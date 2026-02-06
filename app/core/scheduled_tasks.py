"""Scheduled task wrappers for the scheduler.

These functions are called by APScheduler when jobs run.
"""

import asyncio
import os
from datetime import datetime

from app.core.logging import get_logger
from app.core.exceptions import ScraperError, AIProcessorError
from app.core.metrics import (
    SCRAPE_REQUESTS_TOTAL,
    SCRAPE_DURATION_SECONDS,
    record_draft_created,
    record_draft_quality_score,
    record_draft_auto_rejected,
)
from app.models.config import load_config, AppConfig, SourceConfig
from app.utils.storage import Storage

logger = get_logger("scheduled_tasks")


async def scheduled_scrape_task(source_name: str) -> dict:
    """Execute a scheduled scrape for a source.

    This is the async version that performs the actual work.

    Args:
        source_name: Name of the source to scrape

    Returns:
        Dict with result info: {"status": str, "error": str|None, "content_hash": str|None}
    """
    import time
    start_time = time.time()

    logger.info(f"Starting scheduled scrape for source: {source_name}")

    result = {
        "status": "failed",
        "error": None,
        "content_hash": None,
    }

    try:
        # Load config
        config_path = os.getenv("CONFIG_PATH", "config.yaml")
        config = load_config(config_path)

        # Find the source
        source = next((s for s in config.sources if s.name == source_name), None)
        if not source:
            result["error"] = f"Source '{source_name}' not found in config"
            logger.error(result["error"])
            return result

        if not source.enabled:
            result["status"] = "skipped"
            result["error"] = "Source is disabled"
            logger.info(f"Skipping disabled source: {source_name}")
            return result

        # Check for API keys
        gemini_key = os.getenv("GEMINI_API_KEY", "")
        if not gemini_key:
            result["error"] = "GEMINI_API_KEY not configured"
            logger.error(result["error"])
            return result

        # Initialize storage
        storage = Storage(data_dir=config.settings.data_dir)

        # Check for existing pending draft
        pending = storage.get_pending_drafts(source_name)
        if pending:
            result["status"] = "skipped"
            result["error"] = "Pending draft already exists"
            logger.info(f"Skipping {source_name}: pending draft exists")
            return result

        # Import scrape function from dashboard
        from app.ui.dashboard import scrape_source

        # Run the scrape (now returns quality_result as well)
        content, content_hash, diff_summary, quality_result = await scrape_source(
            source, config, gemini_key
        )

        result["content_hash"] = content_hash

        # Check if content changed
        latest = storage.get_latest_version(source_name)
        if latest and latest.content_hash == content_hash:
            result["status"] = "no_changes"
            storage.add_execution(
                source_name=source_name,
                status="no_changes",
                content_hash=content_hash,
            )
            logger.info(f"No changes detected for {source_name}")
        else:
            # Prepare quality data
            quality_score = quality_result.score if quality_result else None
            quality_details = quality_result.to_json() if quality_result else None

            # Record quality metrics
            if quality_score is not None:
                record_draft_quality_score(source_name, quality_score)

            # Create draft for review
            draft = storage.create_draft(
                source_name,
                content,
                content_hash,
                diff_summary,
                quality_score=quality_score,
                quality_details=quality_details,
            )

            # Handle auto-reject based on quality threshold
            if (quality_result and
                config.settings.quality_scoring_enabled and
                quality_result.score <= config.settings.quality_auto_reject_threshold):
                storage.reject_draft(draft.id)
                record_draft_auto_rejected(source_name)
                storage.add_execution(
                    source_name=source_name,
                    status="auto_rejected",
                    content_hash=content_hash,
                    diff_summary=f"Auto-rejected: quality score {quality_result.score} below threshold {config.settings.quality_auto_reject_threshold}",
                )
                result["status"] = "auto_rejected"
                logger.info(f"Draft auto-rejected for {source_name} (quality score: {quality_result.score})")
            else:
                storage.add_execution(
                    source_name=source_name,
                    status="draft_created",
                    content_hash=content_hash,
                    diff_summary=diff_summary,
                )
                result["status"] = "draft_created"
                record_draft_created(source_name)
                logger.info(f"Draft created for {source_name}")

        # Record metrics
        SCRAPE_REQUESTS_TOTAL.labels(source_name=source_name, status="success").inc()

    except ScraperError as e:
        result["error"] = f"Scraping error: {e}"
        logger.error(f"Scheduled scrape failed for {source_name}: {e}")
        SCRAPE_REQUESTS_TOTAL.labels(source_name=source_name, status="error").inc()

        # Record execution failure
        try:
            storage = Storage(data_dir="data")
            storage.add_execution(
                source_name=source_name,
                status="failed",
                error=str(e),
            )
        except Exception:
            pass

    except AIProcessorError as e:
        result["error"] = f"AI processing error: {e}"
        logger.error(f"Scheduled scrape failed for {source_name}: {e}")
        SCRAPE_REQUESTS_TOTAL.labels(source_name=source_name, status="error").inc()

        try:
            storage = Storage(data_dir="data")
            storage.add_execution(
                source_name=source_name,
                status="failed",
                error=str(e),
            )
        except Exception:
            pass

    except Exception as e:
        result["error"] = f"Unexpected error: {e}"
        logger.error(f"Scheduled scrape failed for {source_name}: {e}", exc_info=True)
        SCRAPE_REQUESTS_TOTAL.labels(source_name=source_name, status="error").inc()

        try:
            storage = Storage(data_dir="data")
            storage.add_execution(
                source_name=source_name,
                status="failed",
                error=f"Unexpected: {e}",
            )
        except Exception:
            pass

    finally:
        duration = time.time() - start_time
        SCRAPE_DURATION_SECONDS.labels(source_name=source_name).observe(duration)
        logger.info(f"Scheduled scrape for {source_name} completed in {duration:.2f}s")

    return result


def run_scheduled_scrape(source_name: str):
    """Synchronous wrapper for scheduled scrape task.

    This is the entry point called by APScheduler.

    Args:
        source_name: Name of the source to scrape
    """
    from app.core.scheduler import get_scheduler
    from app.core.metrics import (
        SCHEDULED_JOB_RUNS_TOTAL,
        SCHEDULED_JOB_DURATION_SECONDS,
    )
    import time

    start_time = time.time()
    logger.info(f"APScheduler triggered scrape for: {source_name}")

    try:
        # Run the async task
        result = asyncio.run(scheduled_scrape_task(source_name))

        # Record job run in scheduler
        scheduler = get_scheduler()
        scheduler.record_job_run(
            source_name,
            status=result["status"],
            error=result.get("error"),
        )

        # Record metrics
        SCHEDULED_JOB_RUNS_TOTAL.labels(
            source_name=source_name,
            status=result["status"],
        ).inc()

    except Exception as e:
        logger.error(f"Failed to run scheduled scrape for {source_name}: {e}", exc_info=True)

        # Record failure
        try:
            scheduler = get_scheduler()
            scheduler.record_job_run(source_name, status="failed", error=str(e))
            SCHEDULED_JOB_RUNS_TOTAL.labels(source_name=source_name, status="error").inc()
        except Exception:
            pass

    finally:
        duration = time.time() - start_time
        try:
            SCHEDULED_JOB_DURATION_SECONDS.labels(source_name=source_name).observe(duration)
        except Exception:
            pass
