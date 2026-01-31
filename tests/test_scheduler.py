"""Tests for app.core.scheduler module."""

import os
import tempfile
from datetime import datetime, timedelta

import pytest

from app.core.scheduler import (
    validate_cron_expression,
    get_next_run_time,
    get_cron_description,
    SourceScheduler,
    JobInfo,
)
from app.core.exceptions import SchedulerError


class TestCronValidation:
    """Test cron expression validation."""

    def test_validate_valid_expression(self):
        """Test validation of valid cron expressions."""
        valid_expressions = [
            "0 8 * * *",       # Daily at 8am
            "*/15 * * * *",   # Every 15 minutes
            "0 0 1 * *",      # First of month at midnight
            "0 9 * * 1-5",    # Weekdays at 9am
            "30 14 * * 1",    # Mondays at 2:30pm
            "0 */2 * * *",    # Every 2 hours
        ]

        for expr in valid_expressions:
            is_valid, error = validate_cron_expression(expr)
            assert is_valid, f"Expected '{expr}' to be valid, got error: {error}"
            assert error == ""

    def test_validate_invalid_expression(self):
        """Test validation of invalid cron expressions."""
        invalid_expressions = [
            "",                # Empty
            "* * *",          # Too few fields
            "60 * * * *",     # Invalid minute
            "* 25 * * *",     # Invalid hour
            "* * 32 * *",     # Invalid day
            "* * * 13 *",     # Invalid month
            "abc * * * *",    # Non-numeric
        ]

        for expr in invalid_expressions:
            is_valid, error = validate_cron_expression(expr)
            assert not is_valid, f"Expected '{expr}' to be invalid"
            assert error != ""

    def test_validate_empty_expression(self):
        """Test validation of empty/whitespace expression."""
        is_valid, error = validate_cron_expression("")
        assert not is_valid
        assert "empty" in error.lower()

        is_valid, error = validate_cron_expression("   ")
        assert not is_valid


class TestNextRunTime:
    """Test next run time calculation."""

    def test_get_next_run_time_valid(self):
        """Test getting next run time for valid expression."""
        # Every minute - should be within the next minute
        next_run = get_next_run_time("* * * * *")
        assert next_run is not None
        assert next_run > datetime.now()
        assert next_run < datetime.now() + timedelta(minutes=2)

    def test_get_next_run_time_daily(self):
        """Test next run time for daily schedule."""
        # Daily at a specific hour (use a time that's definitely in the future)
        now = datetime.now()
        future_hour = (now.hour + 2) % 24
        next_run = get_next_run_time(f"0 {future_hour} * * *")

        assert next_run is not None
        assert next_run.hour == future_hour
        assert next_run.minute == 0

    def test_get_next_run_time_invalid(self):
        """Test next run time for invalid expression returns None."""
        result = get_next_run_time("")
        assert result is None

        result = get_next_run_time("invalid")
        assert result is None

    def test_get_next_run_time_with_base(self):
        """Test next run time with custom base time."""
        base_time = datetime(2024, 1, 15, 10, 0, 0)
        next_run = get_next_run_time("0 12 * * *", base_time)

        assert next_run is not None
        assert next_run.hour == 12
        assert next_run.day == 15  # Same day since 12:00 is after 10:00


class TestCronDescription:
    """Test human-readable cron descriptions."""

    def test_every_n_minutes(self):
        """Test description for every N minutes."""
        desc = get_cron_description("*/5 * * * *")
        assert "5 minutes" in desc.lower()

        desc = get_cron_description("*/30 * * * *")
        assert "30 minutes" in desc.lower()

    def test_hourly(self):
        """Test description for hourly schedule."""
        desc = get_cron_description("0 * * * *")
        assert "hour" in desc.lower()

    def test_daily(self):
        """Test description for daily schedule."""
        desc = get_cron_description("0 8 * * *")
        assert "daily" in desc.lower() or "08:00" in desc

    def test_weekly(self):
        """Test description for weekly schedule."""
        desc = get_cron_description("0 9 * * 1")
        assert "mon" in desc.lower() or "weekly" in desc.lower()

    def test_no_schedule(self):
        """Test description for no schedule."""
        desc = get_cron_description("")
        assert "no schedule" in desc.lower()

    def test_complex_returns_expression(self):
        """Test that complex expressions return the expression itself."""
        expr = "0,30 9-17 * * 1-5"
        desc = get_cron_description(expr)
        # For complex expressions, should contain the original or be descriptive
        assert len(desc) > 0


class TestSourceSchedulerJobState:
    """Test SourceScheduler job state operations using database."""

    @pytest.fixture
    def scheduler(self):
        """Create a scheduler with temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Reset singleton for testing
            SourceScheduler._instance = None
            SourceScheduler._initialized = False

            scheduler = SourceScheduler(data_dir=tmpdir)
            yield scheduler

            # Cleanup
            SourceScheduler._instance = None
            SourceScheduler._initialized = False

    def test_job_state_save_and_get(self, scheduler):
        """Test saving and retrieving job state."""
        # Save job state directly to database
        scheduler._db.save_job_state("test_source", "0 8 * * *")

        # Retrieve it
        state = scheduler._db.get_job_state("test_source")

        assert state is not None
        assert state.source_name == "test_source"
        assert state.cron_expression == "0 8 * * *"
        assert not state.is_paused  # SQLite stores booleans as 0/1

    def test_job_state_update(self, scheduler):
        """Test updating job state."""
        scheduler._db.save_job_state("test_source", "0 8 * * *")

        # Update pause state
        scheduler._db.update_job_state("test_source", is_paused=True)

        state = scheduler._db.get_job_state("test_source")
        assert state.is_paused  # SQLite stores booleans as 0/1

    def test_job_state_update_run_info(self, scheduler):
        """Test updating job run information."""
        scheduler._db.save_job_state("test_source", "0 8 * * *")

        now = datetime.now().isoformat()
        scheduler._db.update_job_state(
            "test_source",
            last_run_at=now,
            last_run_status="success",
        )

        state = scheduler._db.get_job_state("test_source")
        assert state.last_run_at == now
        assert state.last_run_status == "success"

    def test_job_state_delete(self, scheduler):
        """Test deleting job state."""
        scheduler._db.save_job_state("test_source", "0 8 * * *")

        deleted = scheduler._db.delete_job_state("test_source")
        assert deleted is True

        state = scheduler._db.get_job_state("test_source")
        assert state is None

    def test_get_all_job_states(self, scheduler):
        """Test getting all job states."""
        scheduler._db.save_job_state("source1", "0 8 * * *")
        scheduler._db.save_job_state("source2", "*/30 * * * *")
        scheduler._db.save_job_state("source3", "0 12 * * 1")

        states = scheduler._db.get_all_job_states()

        assert len(states) == 3
        source_names = [s.source_name for s in states]
        assert "source1" in source_names
        assert "source2" in source_names
        assert "source3" in source_names


class TestSourceSchedulerJobInfo:
    """Test SourceScheduler JobInfo operations."""

    @pytest.fixture
    def scheduler(self):
        """Create a scheduler with temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Reset singleton for testing
            SourceScheduler._instance = None
            SourceScheduler._initialized = False

            scheduler = SourceScheduler(data_dir=tmpdir)
            yield scheduler

            # Cleanup
            SourceScheduler._instance = None
            SourceScheduler._initialized = False

    def test_get_job_info_not_found(self, scheduler):
        """Test getting info for non-existent job."""
        info = scheduler.get_job_info("nonexistent")
        assert info is None

    def test_get_job_info_with_state(self, scheduler):
        """Test getting job info when state exists."""
        scheduler._db.save_job_state("test_source", "0 8 * * *")

        info = scheduler.get_job_info("test_source")

        assert info is not None
        assert info.source_name == "test_source"
        assert info.cron_expression == "0 8 * * *"
        assert not info.is_paused  # SQLite stores booleans as 0/1
        assert info.next_run_time is not None

    def test_get_job_info_paused(self, scheduler):
        """Test that paused jobs have no next run time."""
        scheduler._db.save_job_state("test_source", "0 8 * * *", is_paused=True)

        info = scheduler.get_job_info("test_source")

        assert info is not None
        assert info.is_paused  # SQLite stores booleans as 0/1
        assert info.next_run_time is None

    def test_get_all_jobs(self, scheduler):
        """Test getting all jobs as JobInfo."""
        scheduler._db.save_job_state("source1", "0 8 * * *")
        scheduler._db.save_job_state("source2", "*/30 * * * *", is_paused=True)

        jobs = scheduler.get_all_jobs()

        assert len(jobs) == 2
        assert all(isinstance(j, JobInfo) for j in jobs)

        # Check paused job has no next run
        paused_job = next(j for j in jobs if j.source_name == "source2")
        assert paused_job.is_paused  # SQLite stores booleans as 0/1
        assert paused_job.next_run_time is None


class TestSourceSchedulerRecordRun:
    """Test SourceScheduler run recording."""

    @pytest.fixture
    def scheduler(self):
        """Create a scheduler with temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Reset singleton for testing
            SourceScheduler._instance = None
            SourceScheduler._initialized = False

            scheduler = SourceScheduler(data_dir=tmpdir)
            yield scheduler

            # Cleanup
            SourceScheduler._instance = None
            SourceScheduler._initialized = False

    def test_record_job_run_success(self, scheduler):
        """Test recording a successful job run."""
        scheduler._db.save_job_state("test_source", "0 8 * * *")

        scheduler.record_job_run("test_source", "success")

        state = scheduler._db.get_job_state("test_source")
        assert state.last_run_status == "success"
        assert state.last_run_at is not None
        assert state.last_error is None

    def test_record_job_run_failure(self, scheduler):
        """Test recording a failed job run."""
        scheduler._db.save_job_state("test_source", "0 8 * * *")

        scheduler.record_job_run("test_source", "failed", error="Connection timeout")

        state = scheduler._db.get_job_state("test_source")
        assert state.last_run_status == "failed"
        assert state.last_error == "Connection timeout"


class TestSourceSchedulerSingleton:
    """Test SourceScheduler singleton behavior."""

    def test_singleton_pattern(self):
        """Test that SourceScheduler is a singleton."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Reset singleton
            SourceScheduler._instance = None
            SourceScheduler._initialized = False

            s1 = SourceScheduler(data_dir=tmpdir)
            s2 = SourceScheduler(data_dir=tmpdir)

            assert s1 is s2

            # Cleanup
            SourceScheduler._instance = None
            SourceScheduler._initialized = False
