"""Prometheus metrics for dynamic-kb observability."""

import functools
import time
from typing import Callable, Optional

from prometheus_client import Counter, Histogram, Gauge, Info, generate_latest, CONTENT_TYPE_LATEST

from app.core.logging import get_logger

logger = get_logger("metrics")

# =============================================================================
# Application Info
# =============================================================================

APP_INFO = Info(
    "dynamic_kb",
    "Dynamic KB application information",
)
APP_INFO.info({
    "version": "0.1.0",
    "component": "dynamic-kb",
})

# =============================================================================
# Scraper Metrics
# =============================================================================

SCRAPE_REQUESTS_TOTAL = Counter(
    "dynamic_kb_scrape_requests_total",
    "Total number of scrape requests",
    ["source_name", "status"],
)

SCRAPE_DURATION_SECONDS = Histogram(
    "dynamic_kb_scrape_duration_seconds",
    "Duration of scrape operations in seconds",
    ["source_name"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600),
)

SCRAPE_PAGES_TOTAL = Counter(
    "dynamic_kb_scrape_pages_total",
    "Total number of pages scraped",
    ["source_name", "status"],
)

# =============================================================================
# AI Processor Metrics
# =============================================================================

AI_REQUESTS_TOTAL = Counter(
    "dynamic_kb_ai_requests_total",
    "Total number of AI processing requests",
    ["operation", "model", "status"],
)

AI_DURATION_SECONDS = Histogram(
    "dynamic_kb_ai_duration_seconds",
    "Duration of AI processing operations in seconds",
    ["operation", "model"],
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120),
)

AI_RETRIES_TOTAL = Counter(
    "dynamic_kb_ai_retries_total",
    "Total number of AI request retries",
    ["operation", "model"],
)

AI_TOKENS_TOTAL = Counter(
    "dynamic_kb_ai_tokens_total",
    "Total tokens used in AI requests",
    ["operation", "model", "token_type"],
)

# =============================================================================
# ElevenLabs API Metrics
# =============================================================================

ELEVENLABS_REQUESTS_TOTAL = Counter(
    "dynamic_kb_elevenlabs_requests_total",
    "Total number of ElevenLabs API requests",
    ["endpoint", "method", "status"],
)

ELEVENLABS_DURATION_SECONDS = Histogram(
    "dynamic_kb_elevenlabs_duration_seconds",
    "Duration of ElevenLabs API requests in seconds",
    ["endpoint", "method"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30),
)

ELEVENLABS_RETRIES_TOTAL = Counter(
    "dynamic_kb_elevenlabs_retries_total",
    "Total number of ElevenLabs API retries",
    ["endpoint", "method"],
)

# =============================================================================
# Knowledge Base Metrics
# =============================================================================

KB_DOCUMENTS_CREATED_TOTAL = Counter(
    "dynamic_kb_kb_documents_created_total",
    "Total number of KB documents created",
    ["source_name"],
)

KB_DOCUMENTS_DELETED_TOTAL = Counter(
    "dynamic_kb_kb_documents_deleted_total",
    "Total number of KB documents deleted",
    ["source_name"],
)

KB_CONTENT_SIZE_BYTES = Histogram(
    "dynamic_kb_kb_content_size_bytes",
    "Size of KB content in bytes",
    ["source_name"],
    buckets=(1000, 10000, 50000, 100000, 500000, 1000000),
)

# =============================================================================
# Draft & Version Metrics
# =============================================================================

DRAFTS_CREATED_TOTAL = Counter(
    "dynamic_kb_drafts_created_total",
    "Total number of content drafts created",
    ["source_name"],
)

DRAFTS_APPROVED_TOTAL = Counter(
    "dynamic_kb_drafts_approved_total",
    "Total number of content drafts approved",
    ["source_name"],
)

DRAFTS_REJECTED_TOTAL = Counter(
    "dynamic_kb_drafts_rejected_total",
    "Total number of content drafts rejected",
    ["source_name"],
)

DRAFTS_PENDING = Gauge(
    "dynamic_kb_drafts_pending",
    "Number of pending content drafts",
    ["source_name"],
)

# =============================================================================
# Health Check Metrics
# =============================================================================

HEALTH_CHECK_STATUS = Gauge(
    "dynamic_kb_health_check_status",
    "Health check status (1=healthy, 0=unhealthy)",
    ["component"],
)

HEALTH_CHECK_DURATION_SECONDS = Histogram(
    "dynamic_kb_health_check_duration_seconds",
    "Duration of health checks in seconds",
    ["component"],
    buckets=(0.1, 0.5, 1, 2, 5),
)

# =============================================================================
# Helper Functions
# =============================================================================


def _persist_metric(metric_name: str, value: float, labels: dict = None):
    """Persist a metric to database storage.

    This is a helper that lazily imports MetricsStorage to avoid circular imports.
    """
    try:
        from app.core.metrics_storage import persist_metric
        persist_metric(metric_name, value, labels)
    except Exception as e:
        # Don't let persistence failures break metrics recording
        logger.debug(f"Failed to persist metric {metric_name}: {e}")


def get_metrics() -> bytes:
    """Generate Prometheus metrics output.

    Returns:
        Prometheus metrics in text format.
    """
    return generate_latest()


def get_metrics_content_type() -> str:
    """Get the content type for Prometheus metrics.

    Returns:
        Content type string.
    """
    return CONTENT_TYPE_LATEST


def track_scrape(source_name: str):
    """Decorator to track scrape operations.

    Usage:
        @track_scrape("my_source")
        async def scrape_my_source():
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"
            try:
                result = await func(*args, **kwargs)
                SCRAPE_REQUESTS_TOTAL.labels(source_name=source_name, status="success").inc()
                return result
            except Exception as e:
                status = "error"
                SCRAPE_REQUESTS_TOTAL.labels(source_name=source_name, status="error").inc()
                raise
            finally:
                duration = time.time() - start_time
                SCRAPE_DURATION_SECONDS.labels(source_name=source_name).observe(duration)
                _persist_metric("scrape_requests_total", 1.0, {
                    "source_name": source_name, "status": status
                })
                _persist_metric("scrape_duration_seconds", duration, {
                    "source_name": source_name
                })

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"
            try:
                result = func(*args, **kwargs)
                SCRAPE_REQUESTS_TOTAL.labels(source_name=source_name, status="success").inc()
                return result
            except Exception as e:
                status = "error"
                SCRAPE_REQUESTS_TOTAL.labels(source_name=source_name, status="error").inc()
                raise
            finally:
                duration = time.time() - start_time
                SCRAPE_DURATION_SECONDS.labels(source_name=source_name).observe(duration)
                _persist_metric("scrape_requests_total", 1.0, {
                    "source_name": source_name, "status": status
                })
                _persist_metric("scrape_duration_seconds", duration, {
                    "source_name": source_name
                })

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def track_ai_operation(operation: str, model: str):
    """Decorator to track AI operations.

    Usage:
        @track_ai_operation("extract_links", "gemini-2.5-flash")
        async def extract_links():
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"
            try:
                result = await func(*args, **kwargs)
                AI_REQUESTS_TOTAL.labels(operation=operation, model=model, status="success").inc()
                return result
            except Exception as e:
                status = "error"
                AI_REQUESTS_TOTAL.labels(operation=operation, model=model, status="error").inc()
                raise
            finally:
                duration = time.time() - start_time
                AI_DURATION_SECONDS.labels(operation=operation, model=model).observe(duration)
                _persist_metric("ai_requests_total", 1.0, {
                    "operation": operation, "model": model, "status": status
                })
                _persist_metric("ai_duration_seconds", duration, {
                    "operation": operation, "model": model
                })

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"
            try:
                result = func(*args, **kwargs)
                AI_REQUESTS_TOTAL.labels(operation=operation, model=model, status="success").inc()
                return result
            except Exception as e:
                status = "error"
                AI_REQUESTS_TOTAL.labels(operation=operation, model=model, status="error").inc()
                raise
            finally:
                duration = time.time() - start_time
                AI_DURATION_SECONDS.labels(operation=operation, model=model).observe(duration)
                _persist_metric("ai_requests_total", 1.0, {
                    "operation": operation, "model": model, "status": status
                })
                _persist_metric("ai_duration_seconds", duration, {
                    "operation": operation, "model": model
                })

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def record_ai_retry(operation: str, model: str):
    """Record an AI retry event."""
    AI_RETRIES_TOTAL.labels(operation=operation, model=model).inc()
    # Persist to database
    _persist_metric("ai_retries_total", 1.0, {"operation": operation, "model": model})


def record_ai_tokens(
    operation: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
):
    """Record AI token usage."""
    if prompt_tokens:
        AI_TOKENS_TOTAL.labels(
            operation=operation, model=model, token_type="prompt"
        ).inc(prompt_tokens)
        _persist_metric("ai_tokens_total", float(prompt_tokens), {
            "operation": operation, "model": model, "token_type": "prompt"
        })
    if completion_tokens:
        AI_TOKENS_TOTAL.labels(
            operation=operation, model=model, token_type="completion"
        ).inc(completion_tokens)
        _persist_metric("ai_tokens_total", float(completion_tokens), {
            "operation": operation, "model": model, "token_type": "completion"
        })


def record_elevenlabs_request(
    endpoint: str,
    method: str,
    status: str,
    duration: float,
):
    """Record an ElevenLabs API request."""
    ELEVENLABS_REQUESTS_TOTAL.labels(
        endpoint=endpoint, method=method, status=status
    ).inc()
    ELEVENLABS_DURATION_SECONDS.labels(endpoint=endpoint, method=method).observe(duration)
    _persist_metric("elevenlabs_requests_total", 1.0, {
        "endpoint": endpoint, "method": method, "status": status
    })
    _persist_metric("elevenlabs_duration_seconds", duration, {
        "endpoint": endpoint, "method": method
    })


def record_elevenlabs_retry(endpoint: str, method: str):
    """Record an ElevenLabs API retry."""
    ELEVENLABS_RETRIES_TOTAL.labels(endpoint=endpoint, method=method).inc()
    _persist_metric("elevenlabs_retries_total", 1.0, {
        "endpoint": endpoint, "method": method
    })


def record_kb_document_created(source_name: str, content_size: int):
    """Record KB document creation."""
    KB_DOCUMENTS_CREATED_TOTAL.labels(source_name=source_name).inc()
    KB_CONTENT_SIZE_BYTES.labels(source_name=source_name).observe(content_size)
    _persist_metric("kb_documents_created_total", 1.0, {"source_name": source_name})
    _persist_metric("kb_content_size_bytes", float(content_size), {"source_name": source_name})


def record_kb_document_deleted(source_name: str):
    """Record KB document deletion."""
    KB_DOCUMENTS_DELETED_TOTAL.labels(source_name=source_name).inc()
    _persist_metric("kb_documents_deleted_total", 1.0, {"source_name": source_name})


def record_draft_created(source_name: str):
    """Record draft creation."""
    DRAFTS_CREATED_TOTAL.labels(source_name=source_name).inc()
    _persist_metric("drafts_created_total", 1.0, {"source_name": source_name})


def record_draft_approved(source_name: str):
    """Record draft approval."""
    DRAFTS_APPROVED_TOTAL.labels(source_name=source_name).inc()
    _persist_metric("drafts_approved_total", 1.0, {"source_name": source_name})


def record_draft_rejected(source_name: str):
    """Record draft rejection."""
    DRAFTS_REJECTED_TOTAL.labels(source_name=source_name).inc()
    _persist_metric("drafts_rejected_total", 1.0, {"source_name": source_name})


def set_pending_drafts(source_name: str, count: int):
    """Set the number of pending drafts for a source."""
    DRAFTS_PENDING.labels(source_name=source_name).set(count)
    _persist_metric("drafts_pending", float(count), {"source_name": source_name})


def record_health_check(component: str, healthy: bool, duration: float):
    """Record a health check result."""
    HEALTH_CHECK_STATUS.labels(component=component).set(1 if healthy else 0)
    HEALTH_CHECK_DURATION_SECONDS.labels(component=component).observe(duration)
    _persist_metric("health_check_status", 1.0 if healthy else 0.0, {"component": component})
    _persist_metric("health_check_duration_seconds", duration, {"component": component})


# =============================================================================
# Scheduler Metrics
# =============================================================================

SCHEDULED_JOB_RUNS_TOTAL = Counter(
    "dynamic_kb_scheduled_job_runs_total",
    "Total number of scheduled job runs",
    ["source_name", "status"],
)

SCHEDULED_JOB_DURATION_SECONDS = Histogram(
    "dynamic_kb_scheduled_job_duration_seconds",
    "Duration of scheduled job executions in seconds",
    ["source_name"],
    buckets=(10, 30, 60, 120, 300, 600, 1200),
)

ACTIVE_SCHEDULED_JOBS = Gauge(
    "dynamic_kb_active_scheduled_jobs",
    "Number of active (non-paused) scheduled jobs",
)


def record_scheduled_job_run(source_name: str, status: str, duration: float):
    """Record a scheduled job run."""
    SCHEDULED_JOB_RUNS_TOTAL.labels(source_name=source_name, status=status).inc()
    SCHEDULED_JOB_DURATION_SECONDS.labels(source_name=source_name).observe(duration)
    _persist_metric("scheduled_job_runs_total", 1.0, {"source_name": source_name, "status": status})
    _persist_metric("scheduled_job_duration_seconds", duration, {"source_name": source_name})


def set_active_scheduled_jobs(count: int):
    """Set the number of active scheduled jobs."""
    ACTIVE_SCHEDULED_JOBS.set(count)
    _persist_metric("active_scheduled_jobs", float(count), {})
