"""APScheduler-based job scheduler for dynamic-kb.

Provides native scheduling with SQLite persistence. Jobs survive app restarts
and the scheduler runs within the Streamlit process.
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass

from croniter import croniter

from app.core.exceptions import SchedulerError
from app.core.logging import get_logger
from app.utils.database import Database, ScheduledJobState

logger = get_logger("scheduler")


@dataclass
class JobInfo:
    """Information about a scheduled job."""

    source_name: str
    cron_expression: str
    is_paused: bool
    next_run_time: Optional[datetime]
    last_run_at: Optional[str]
    last_run_status: Optional[str]
    last_error: Optional[str]


def validate_cron_expression(cron_expr: str) -> tuple[bool, str]:
    """Validate a cron expression.

    Args:
        cron_expr: Cron expression string (5 fields: min hour day month weekday)

    Returns:
        Tuple of (is_valid, error_message). error_message is empty if valid.
    """
    if not cron_expr or not cron_expr.strip():
        return False, "Cron expression cannot be empty"

    try:
        # croniter validates the expression when creating an iterator
        croniter(cron_expr, datetime.now())
        return True, ""
    except (ValueError, KeyError) as e:
        return False, f"Invalid cron expression: {e}"


def get_next_run_time(cron_expr: str, base_time: Optional[datetime] = None) -> Optional[datetime]:
    """Get the next run time for a cron expression.

    Args:
        cron_expr: Cron expression string
        base_time: Base time to calculate from (defaults to now)

    Returns:
        Next run time as datetime, or None if invalid expression
    """
    if not cron_expr:
        return None

    try:
        base = base_time or datetime.now()
        cron = croniter(cron_expr, base)
        return cron.get_next(datetime)
    except (ValueError, KeyError):
        return None


def get_cron_description(cron_expr: str) -> str:
    """Get a human-readable description of a cron expression.

    Args:
        cron_expr: Cron expression string

    Returns:
        Human-readable description
    """
    if not cron_expr:
        return "No schedule"

    # Common patterns
    parts = cron_expr.split()
    if len(parts) != 5:
        return cron_expr

    minute, hour, day, month, weekday = parts

    # Every N minutes
    if minute.startswith("*/") and hour == "*" and day == "*" and month == "*" and weekday == "*":
        interval = minute[2:]
        return f"Every {interval} minutes"

    # Every hour at specific minute
    if minute.isdigit() and hour == "*" and day == "*" and month == "*" and weekday == "*":
        return f"Every hour at :{minute.zfill(2)}"

    # Daily at specific time
    if minute.isdigit() and hour.isdigit() and day == "*" and month == "*" and weekday == "*":
        return f"Daily at {hour.zfill(2)}:{minute.zfill(2)}"

    # Weekly on specific day
    if minute.isdigit() and hour.isdigit() and day == "*" and month == "*" and weekday.isdigit():
        days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        day_name = days[int(weekday)] if 0 <= int(weekday) <= 6 else weekday
        return f"Weekly on {day_name} at {hour.zfill(2)}:{minute.zfill(2)}"

    return cron_expr


class SourceScheduler:
    """Singleton scheduler for managing source scrape jobs.

    Uses APScheduler with SQLite job store for persistence. Jobs are tracked
    in a separate table for additional metadata (pause state, last run info).
    """

    _instance: Optional["SourceScheduler"] = None
    _initialized: bool = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, data_dir: str = "data"):
        """Initialize the scheduler.

        Args:
            data_dir: Directory for data storage (scheduler DB will be here)
        """
        # Only initialize once (singleton pattern)
        if SourceScheduler._initialized:
            return

        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Use same database as the rest of the app
        db_path = self.data_dir / "kb_sync.db"
        self._db = Database(str(db_path))

        # APScheduler setup
        self._scheduler = None
        self._task_func: Optional[Callable] = None

        SourceScheduler._initialized = True
        logger.info("SourceScheduler initialized")

    def _ensure_scheduler(self):
        """Ensure APScheduler is initialized."""
        if self._scheduler is not None:
            return

        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
            from apscheduler.executors.pool import ThreadPoolExecutor

            # Create SQLAlchemy job store for persistence
            scheduler_db_path = self.data_dir / "scheduler_jobs.db"

            jobstores = {
                'default': SQLAlchemyJobStore(url=f'sqlite:///{scheduler_db_path}')
            }

            executors = {
                'default': ThreadPoolExecutor(10)
            }

            job_defaults = {
                'coalesce': True,  # Combine missed runs into one
                'max_instances': 1,  # Only one instance of each job at a time
                'misfire_grace_time': 3600,  # Allow jobs to run up to 1 hour late
            }

            self._scheduler = BackgroundScheduler(
                jobstores=jobstores,
                executors=executors,
                job_defaults=job_defaults,
            )

            logger.info(f"APScheduler initialized with SQLite store at {scheduler_db_path}")

        except ImportError as e:
            logger.error(f"Failed to import APScheduler: {e}")
            raise SchedulerError(f"APScheduler not installed: {e}")

    def set_task_function(self, func: Callable[[str], None]):
        """Set the function to call when a job runs.

        Args:
            func: Function that takes source_name as argument
        """
        self._task_func = func

    def start(self):
        """Start the scheduler."""
        self._ensure_scheduler()

        if not self._scheduler.running:
            try:
                self._scheduler.start()
                logger.info("Scheduler started")
            except Exception as e:
                logger.error(f"Failed to start scheduler: {e}")
                raise SchedulerError(f"Failed to start scheduler: {e}")

    def stop(self):
        """Stop the scheduler."""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        if self._scheduler is None:
            return False
        return self._scheduler.running

    def add_job(self, source_name: str, cron_expression: str) -> JobInfo:
        """Add or update a scheduled job for a source.

        Args:
            source_name: Name of the source to schedule
            cron_expression: Cron expression for the schedule

        Returns:
            JobInfo for the created/updated job

        Raises:
            SchedulerError: If cron expression is invalid
        """
        valid, error = validate_cron_expression(cron_expression)
        if not valid:
            raise SchedulerError(error)

        self._ensure_scheduler()

        try:
            from apscheduler.triggers.cron import CronTrigger

            # Parse cron expression
            parts = cron_expression.split()
            if len(parts) != 5:
                raise SchedulerError(f"Invalid cron expression format: {cron_expression}")

            minute, hour, day, month, weekday = parts

            trigger = CronTrigger(
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=weekday,
            )

            # Create job ID from source name
            job_id = f"scrape_{source_name}"

            # Define the job function wrapper
            def job_func(src_name=source_name):
                if self._task_func:
                    self._task_func(src_name)
                else:
                    logger.warning(f"No task function set for job {job_id}")

            # Remove existing job if any
            existing = self._scheduler.get_job(job_id)
            if existing:
                self._scheduler.remove_job(job_id)

            # Add job to APScheduler
            self._scheduler.add_job(
                job_func,
                trigger,
                id=job_id,
                name=f"Scrape {source_name}",
                replace_existing=True,
            )

            # Save state to our database
            self._db.save_job_state(source_name, cron_expression)

            logger.info(f"Added/updated job for source '{source_name}' with schedule '{cron_expression}'")

            return self.get_job_info(source_name)

        except Exception as e:
            logger.error(f"Failed to add job for source '{source_name}': {e}")
            raise SchedulerError(f"Failed to add job: {e}")

    def remove_job(self, source_name: str) -> bool:
        """Remove a scheduled job.

        Args:
            source_name: Name of the source

        Returns:
            True if job was removed, False if not found
        """
        self._ensure_scheduler()

        job_id = f"scrape_{source_name}"

        try:
            existing = self._scheduler.get_job(job_id)
            if existing:
                self._scheduler.remove_job(job_id)
            self._db.delete_job_state(source_name)
            logger.info(f"Removed job for source '{source_name}'")
            return True
        except Exception as e:
            logger.debug(f"Job not found for source '{source_name}': {e}")
            # Still try to clean up database state
            self._db.delete_job_state(source_name)
            return False

    def pause_job(self, source_name: str) -> bool:
        """Pause a scheduled job.

        Args:
            source_name: Name of the source

        Returns:
            True if job was paused
        """
        self._ensure_scheduler()

        job_id = f"scrape_{source_name}"

        try:
            job = self._scheduler.get_job(job_id)
            if job:
                self._scheduler.pause_job(job_id)
            self._db.update_job_state(source_name, is_paused=True)
            logger.info(f"Paused job for source '{source_name}'")
            return True
        except Exception as e:
            logger.error(f"Failed to pause job for source '{source_name}': {e}")
            return False

    def resume_job(self, source_name: str) -> bool:
        """Resume a paused scheduled job.

        Args:
            source_name: Name of the source

        Returns:
            True if job was resumed
        """
        self._ensure_scheduler()

        job_id = f"scrape_{source_name}"

        try:
            job = self._scheduler.get_job(job_id)
            if job:
                self._scheduler.resume_job(job_id)
            self._db.update_job_state(source_name, is_paused=False)
            logger.info(f"Resumed job for source '{source_name}'")
            return True
        except Exception as e:
            logger.error(f"Failed to resume job for source '{source_name}': {e}")
            return False

    def get_job_info(self, source_name: str) -> Optional[JobInfo]:
        """Get information about a scheduled job.

        Args:
            source_name: Name of the source

        Returns:
            JobInfo or None if not found
        """
        state = self._db.get_job_state(source_name)
        if not state:
            return None

        next_run = None
        if not state.is_paused:
            next_run = get_next_run_time(state.cron_expression)

        return JobInfo(
            source_name=state.source_name,
            cron_expression=state.cron_expression,
            is_paused=state.is_paused,
            next_run_time=next_run,
            last_run_at=state.last_run_at,
            last_run_status=state.last_run_status,
            last_error=state.last_error,
        )

    def get_all_jobs(self) -> list[JobInfo]:
        """Get information about all scheduled jobs.

        Returns:
            List of JobInfo for all jobs
        """
        states = self._db.get_all_job_states()
        jobs = []

        for state in states:
            next_run = None
            if not state.is_paused:
                next_run = get_next_run_time(state.cron_expression)

            jobs.append(JobInfo(
                source_name=state.source_name,
                cron_expression=state.cron_expression,
                is_paused=state.is_paused,
                next_run_time=next_run,
                last_run_at=state.last_run_at,
                last_run_status=state.last_run_status,
                last_error=state.last_error,
            ))

        return jobs

    def record_job_run(
        self,
        source_name: str,
        status: str,
        error: Optional[str] = None,
    ):
        """Record that a job ran.

        Args:
            source_name: Name of the source
            status: Run status (success, failed, no_changes, draft_created)
            error: Error message if failed
        """
        now = datetime.now().isoformat()
        self._db.update_job_state(
            source_name,
            last_run_at=now,
            last_run_status=status,
            last_error=error,
        )

    def sync_with_config(self, sources: list) -> dict:
        """Sync scheduler jobs with config sources.

        Adds/updates jobs for sources with schedules, removes jobs for
        sources that no longer have schedules.

        Args:
            sources: List of SourceConfig objects

        Returns:
            Dict with counts: {"added": N, "updated": N, "removed": N, "paused": N}
        """
        self._ensure_scheduler()

        result = {"added": 0, "updated": 0, "removed": 0, "paused": 0}

        # Get current job states
        current_jobs = {state.source_name: state for state in self._db.get_all_job_states()}

        # Track which sources have schedules
        sources_with_schedules = set()

        for source in sources:
            if not source.schedule:
                continue

            sources_with_schedules.add(source.name)

            existing = current_jobs.get(source.name)

            # Check if we need to add/update
            if not existing:
                # New job
                try:
                    self.add_job(source.name, source.schedule)
                    result["added"] += 1

                    # Pause if schedule_enabled is False
                    if not source.schedule_enabled:
                        self.pause_job(source.name)
                        result["paused"] += 1

                except SchedulerError as e:
                    logger.warning(f"Failed to add job for '{source.name}': {e}")

            elif existing.cron_expression != source.schedule:
                # Update schedule
                try:
                    self.add_job(source.name, source.schedule)
                    result["updated"] += 1
                except SchedulerError as e:
                    logger.warning(f"Failed to update job for '{source.name}': {e}")

            # Handle pause state changes
            if existing and source.schedule_enabled and existing.is_paused:
                self.resume_job(source.name)
            elif existing and not source.schedule_enabled and not existing.is_paused:
                self.pause_job(source.name)
                result["paused"] += 1

        # Remove jobs for sources that no longer have schedules
        for source_name in current_jobs:
            if source_name not in sources_with_schedules:
                self.remove_job(source_name)
                result["removed"] += 1

        logger.info(
            f"Scheduler sync complete: {result['added']} added, "
            f"{result['updated']} updated, {result['removed']} removed, "
            f"{result['paused']} paused"
        )

        return result

    def pause_all(self):
        """Pause all scheduled jobs."""
        for job in self.get_all_jobs():
            if not job.is_paused:
                self.pause_job(job.source_name)

    def resume_all(self):
        """Resume all paused jobs."""
        for job in self.get_all_jobs():
            if job.is_paused:
                self.resume_job(job.source_name)


# Module-level singleton getter
_scheduler_instance: Optional[SourceScheduler] = None


def get_scheduler(data_dir: str = "data") -> SourceScheduler:
    """Get the scheduler singleton instance.

    Args:
        data_dir: Directory for data storage

    Returns:
        SourceScheduler singleton instance
    """
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = SourceScheduler(data_dir)
    return _scheduler_instance
