"""Tests for the metrics storage module."""

import os
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.core.metrics_storage import (
    MetricsStorage,
    MetricsSummary,
    get_metrics_storage,
    persist_metric,
    persist_counter,
)
from app.utils.database import MetricEvent


class TestMetricsStorage:
    """Test MetricsStorage class."""

    def test_init_with_sqlite(self):
        """Should initialize with SQLite when Supabase not configured."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SUPABASE_URL", None)
            os.environ.pop("SUPABASE_KEY", None)

            with patch("app.utils.database.Database") as mock_db:
                storage = MetricsStorage()
                assert storage.is_enabled()
                mock_db.assert_called_once()

    def test_init_with_supabase(self):
        """Should initialize with Supabase when configured."""
        with patch.dict(os.environ, {
            "SUPABASE_URL": "https://test.supabase.co",
            "SUPABASE_KEY": "test-key",
        }):
            with patch("app.utils.supabase_db.SupabaseDatabase") as mock_db:
                storage = MetricsStorage()
                assert storage.is_enabled()
                mock_db.assert_called_once()

    def test_record_metric(self):
        """Should record a metric to database."""
        mock_db = MagicMock()
        mock_db.save_metric.return_value = MetricEvent(
            id=1,
            timestamp="2024-01-01T00:00:00",
            metric_name="test_metric",
            metric_value=42.0,
            labels={"key": "value"},
        )

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SUPABASE_URL", None)
            os.environ.pop("SUPABASE_KEY", None)

            storage = MetricsStorage()
            storage._db = mock_db
            storage._enabled = True

            result = storage.record("test_metric", 42.0, {"key": "value"})

            assert result is not None
            assert result.metric_name == "test_metric"
            assert result.metric_value == 42.0
            mock_db.save_metric.assert_called_once_with(
                metric_name="test_metric",
                metric_value=42.0,
                labels={"key": "value"},
            )

    def test_record_metric_when_disabled(self):
        """Should return None when storage is disabled."""
        storage = MetricsStorage()
        storage._enabled = False

        result = storage.record("test_metric", 42.0)
        assert result is None

    def test_get_events(self):
        """Should retrieve metric events."""
        mock_db = MagicMock()
        mock_db.get_metrics.return_value = [
            MetricEvent(
                id=1,
                timestamp="2024-01-01T00:00:00",
                metric_name="test_metric",
                metric_value=42.0,
                labels={},
            ),
        ]

        storage = MetricsStorage()
        storage._db = mock_db
        storage._enabled = True

        events = storage.get_events(metric_name="test_metric")

        assert len(events) == 1
        assert events[0].metric_name == "test_metric"

    def test_get_summary(self):
        """Should return metric summary."""
        mock_db = MagicMock()
        mock_db.get_metric_summary.return_value = {
            "count": 10,
            "total": 100.0,
            "avg": 10.0,
            "min": 5.0,
            "max": 15.0,
        }

        storage = MetricsStorage()
        storage._db = mock_db
        storage._enabled = True

        summary = storage.get_summary("test_metric", hours=24)

        assert isinstance(summary, MetricsSummary)
        assert summary.count == 10
        assert summary.total == 100.0
        assert summary.avg == 10.0

    def test_get_summary_when_disabled(self):
        """Should return empty summary when disabled."""
        storage = MetricsStorage()
        storage._enabled = False

        summary = storage.get_summary("test_metric")

        assert summary.count == 0
        assert summary.total == 0

    def test_get_time_series(self):
        """Should return time series data."""
        mock_db = MagicMock()
        mock_db.get_metrics.return_value = [
            MetricEvent(
                id=1,
                timestamp="2024-01-01T00:00:00",
                metric_name="test_metric",
                metric_value=10.0,
                labels={"type": "a"},
            ),
            MetricEvent(
                id=2,
                timestamp="2024-01-01T01:00:00",
                metric_name="test_metric",
                metric_value=20.0,
                labels={"type": "b"},
            ),
        ]

        storage = MetricsStorage()
        storage._db = mock_db
        storage._enabled = True

        data = storage.get_time_series("test_metric", hours=24)

        assert len(data) == 2
        assert data[0]["value"] == 10.0
        assert data[1]["value"] == 20.0

    def test_cleanup(self):
        """Should cleanup old metrics."""
        mock_db = MagicMock()
        mock_db.cleanup_old_metrics.return_value = 5

        storage = MetricsStorage()
        storage._db = mock_db
        storage._enabled = True

        deleted = storage.cleanup(days=30)

        assert deleted == 5
        mock_db.cleanup_old_metrics.assert_called_once_with(days=30)


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_persist_metric(self):
        """Should persist metric via storage instance."""
        mock_storage = MagicMock()

        with patch("app.core.metrics_storage._metrics_storage", mock_storage):
            with patch("app.core.metrics_storage.get_metrics_storage", return_value=mock_storage):
                persist_metric("test_metric", 42.0, {"key": "value"})

                mock_storage.record.assert_called_once_with(
                    "test_metric", 42.0, {"key": "value"}
                )

    def test_persist_counter(self):
        """Should persist counter with value=1."""
        mock_storage = MagicMock()

        with patch("app.core.metrics_storage._metrics_storage", mock_storage):
            with patch("app.core.metrics_storage.get_metrics_storage", return_value=mock_storage):
                persist_counter("test_counter", {"source": "test"})

                mock_storage.record.assert_called_once_with(
                    "test_counter", 1.0, {"source": "test"}
                )


class TestGetMetricsStorage:
    """Test get_metrics_storage singleton."""

    def test_returns_singleton(self):
        """Should return the same instance."""
        # Reset global
        import app.core.metrics_storage
        app.core.metrics_storage._metrics_storage = None

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SUPABASE_URL", None)
            os.environ.pop("SUPABASE_KEY", None)

            with patch("app.utils.database.Database"):
                storage1 = get_metrics_storage()
                storage2 = get_metrics_storage()

                assert storage1 is storage2
