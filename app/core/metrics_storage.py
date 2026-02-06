"""Metrics persistence to database (Supabase/SQLite)."""

import os
from datetime import datetime, timezone, timedelta
from typing import Optional
from dataclasses import dataclass

from app.core.logging import get_logger
from app.utils.database import MetricEvent

logger = get_logger("metrics_storage")

# Global metrics storage instance
_metrics_storage = None


@dataclass
class MetricsSummary:
    """Summary statistics for a metric over a time period."""

    metric_name: str
    count: int
    total: float
    avg: float
    min: float
    max: float
    start_time: Optional[str] = None
    end_time: Optional[str] = None


def get_metrics_storage():
    """Get or create the metrics storage instance."""
    global _metrics_storage

    if _metrics_storage is None:
        _metrics_storage = MetricsStorage()

    return _metrics_storage


class MetricsStorage:
    """Handles persisting metrics to database."""

    def __init__(self):
        """Initialize metrics storage with database backend."""
        self._db = None
        self._enabled = True

        # Check if we should use Supabase or SQLite
        if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"):
            try:
                from app.utils.supabase_db import SupabaseDatabase
                self._db = SupabaseDatabase()
                logger.info("MetricsStorage initialized with Supabase backend")
            except Exception as e:
                logger.warning(f"Failed to initialize Supabase for metrics: {e}")
                self._enabled = False
        else:
            try:
                from app.utils.database import Database
                data_dir = os.getenv("DATA_DIR", "data")
                self._db = Database(f"{data_dir}/kb_sync.db")
                logger.info("MetricsStorage initialized with SQLite backend")
            except Exception as e:
                logger.warning(f"Failed to initialize SQLite for metrics: {e}")
                self._enabled = False

    def is_enabled(self) -> bool:
        """Check if metrics storage is enabled."""
        return self._enabled and self._db is not None

    def record(
        self,
        metric_name: str,
        value: float,
        labels: Optional[dict] = None,
    ) -> Optional[MetricEvent]:
        """Record a metric event.

        Args:
            metric_name: Name of the metric (e.g., "ai_requests_total")
            value: Numeric value (for counters, this is usually 1)
            labels: Optional dict of label key-values

        Returns:
            MetricEvent if saved successfully, None otherwise.
        """
        if not self.is_enabled():
            return None

        try:
            return self._db.save_metric(
                metric_name=metric_name,
                metric_value=value,
                labels=labels,
            )
        except Exception as e:
            logger.warning(f"Failed to save metric {metric_name}: {e}")
            return None

    def get_events(
        self,
        metric_name: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        labels: Optional[dict] = None,
        limit: int = 1000,
    ) -> list[MetricEvent]:
        """Get metric events with optional filtering.

        Args:
            metric_name: Filter by metric name
            start_time: ISO timestamp for start of range
            end_time: ISO timestamp for end of range
            labels: Filter by label values
            limit: Maximum number of events to return

        Returns:
            List of MetricEvent objects.
        """
        if not self.is_enabled():
            return []

        try:
            return self._db.get_metrics(
                metric_name=metric_name,
                start_time=start_time,
                end_time=end_time,
                labels=labels,
                limit=limit,
            )
        except Exception as e:
            logger.warning(f"Failed to get metrics: {e}")
            return []

    def get_summary(
        self,
        metric_name: str,
        hours: int = 24,
        labels: Optional[dict] = None,
    ) -> MetricsSummary:
        """Get summary statistics for a metric over a time period.

        Args:
            metric_name: Name of the metric
            hours: Number of hours to look back
            labels: Filter by label values

        Returns:
            MetricsSummary with statistics.
        """
        end_time = datetime.now(timezone.utc).isoformat()
        start_time = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        if not self.is_enabled():
            return MetricsSummary(
                metric_name=metric_name,
                count=0,
                total=0,
                avg=0,
                min=0,
                max=0,
                start_time=start_time,
                end_time=end_time,
            )

        try:
            summary = self._db.get_metric_summary(
                metric_name=metric_name,
                start_time=start_time,
                end_time=end_time,
                labels=labels,
            )
            return MetricsSummary(
                metric_name=metric_name,
                count=summary["count"],
                total=summary["total"],
                avg=summary["avg"],
                min=summary["min"],
                max=summary["max"],
                start_time=start_time,
                end_time=end_time,
            )
        except Exception as e:
            logger.warning(f"Failed to get metric summary: {e}")
            return MetricsSummary(
                metric_name=metric_name,
                count=0,
                total=0,
                avg=0,
                min=0,
                max=0,
                start_time=start_time,
                end_time=end_time,
            )

    def get_time_series(
        self,
        metric_name: str,
        hours: int = 24,
        labels: Optional[dict] = None,
    ) -> list[dict]:
        """Get time series data for a metric.

        Args:
            metric_name: Name of the metric
            hours: Number of hours to look back
            labels: Filter by label values

        Returns:
            List of dicts with timestamp and value.
        """
        end_time = datetime.now(timezone.utc).isoformat()
        start_time = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        events = self.get_events(
            metric_name=metric_name,
            start_time=start_time,
            end_time=end_time,
            labels=labels,
            limit=10000,
        )

        return [
            {"timestamp": e.timestamp, "value": e.metric_value, "labels": e.labels}
            for e in sorted(events, key=lambda x: x.timestamp)
        ]

    def cleanup(self, days: int = 30) -> int:
        """Clean up old metrics.

        Args:
            days: Delete metrics older than this many days

        Returns:
            Number of deleted records.
        """
        if not self.is_enabled():
            return 0

        try:
            return self._db.cleanup_old_metrics(days=days)
        except Exception as e:
            logger.warning(f"Failed to cleanup old metrics: {e}")
            return 0


# =============================================================================
# Convenience functions for recording metrics with persistence
# =============================================================================


def persist_metric(
    metric_name: str,
    value: float,
    labels: Optional[dict] = None,
) -> None:
    """Record a metric event to persistent storage.

    This is a convenience function that gets or creates the storage instance.

    Args:
        metric_name: Name of the metric
        value: Numeric value
        labels: Optional label key-values
    """
    storage = get_metrics_storage()
    storage.record(metric_name, value, labels)


def persist_counter(
    metric_name: str,
    labels: Optional[dict] = None,
) -> None:
    """Record a counter increment (value=1) to persistent storage.

    Args:
        metric_name: Name of the counter metric
        labels: Optional label key-values
    """
    persist_metric(metric_name, 1.0, labels)
