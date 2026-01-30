"""Supabase database backend for content storage and versioning."""

import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from supabase import create_client, Client

from app.utils.database import ContentVersion, ContentDraft, ExecutionRecord, MetricEvent


class SupabaseDatabase:
    """Supabase database manager for dynamic-kb."""

    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")
        self.client: Client = create_client(url, key)

    def _now_iso(self) -> str:
        """Get current UTC timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()

    def _row_to_version(self, row: dict) -> ContentVersion:
        """Convert a Supabase row to ContentVersion."""
        return ContentVersion(
            id=row["id"],
            source_name=row["source_name"],
            content=row["content"],
            content_hash=row["content_hash"],
            created_at=row["created_at"],
            doc_id=row.get("doc_id"),
            pushed_at=row.get("pushed_at"),
            version_number=row.get("version_number", 1),
        )

    def _row_to_draft(self, row: dict) -> ContentDraft:
        """Convert a Supabase row to ContentDraft."""
        return ContentDraft(
            id=row["id"],
            source_name=row["source_name"],
            content=row["content"],
            content_hash=row["content_hash"],
            created_at=row["created_at"],
            status=row["status"],
            diff_summary=row.get("diff_summary"),
            previous_version_id=row.get("previous_version_id"),
        )

    def _row_to_execution(self, row: dict) -> ExecutionRecord:
        """Convert a Supabase row to ExecutionRecord."""
        return ExecutionRecord(
            id=row["id"],
            source_name=row["source_name"],
            timestamp=row["timestamp"],
            status=row["status"],
            content_hash=row.get("content_hash"),
            doc_id=row.get("doc_id"),
            error=row.get("error"),
            diff_summary=row.get("diff_summary"),
            version_id=row.get("version_id"),
        )

    def _row_to_metric(self, row: dict) -> MetricEvent:
        """Convert a Supabase row to MetricEvent."""
        return MetricEvent(
            id=row["id"],
            timestamp=row["timestamp"],
            metric_name=row["metric_name"],
            metric_value=row["metric_value"],
            labels=row.get("labels") or {},
        )

    # Content Versions
    def save_version(
        self,
        source_name: str,
        content: str,
        content_hash: str,
        doc_id: Optional[str] = None,
    ) -> ContentVersion:
        """Save a new content version."""
        now = self._now_iso()

        # Get next version number
        result = (
            self.client.table("content_versions")
            .select("version_number")
            .eq("source_name", source_name)
            .order("version_number", desc=True)
            .limit(1)
            .execute()
        )
        version_number = (result.data[0]["version_number"] if result.data else 0) + 1

        # Try to insert, handle conflict by updating
        data = {
            "source_name": source_name,
            "content": content,
            "content_hash": content_hash,
            "created_at": now,
            "doc_id": doc_id,
            "pushed_at": now if doc_id else None,
            "version_number": version_number,
        }

        # Use upsert with on_conflict to handle duplicates
        result = (
            self.client.table("content_versions")
            .upsert(data, on_conflict="source_name,content_hash")
            .execute()
        )

        row = result.data[0]
        return self._row_to_version(row)

    def get_latest_version(self, source_name: str) -> Optional[ContentVersion]:
        """Get the most recent version for a source."""
        result = (
            self.client.table("content_versions")
            .select("*")
            .eq("source_name", source_name)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if result.data:
            return self._row_to_version(result.data[0])
        return None

    def get_versions(self, source_name: str, limit: int = 10) -> list[ContentVersion]:
        """Get version history for a source."""
        result = (
            self.client.table("content_versions")
            .select("*")
            .eq("source_name", source_name)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        return [self._row_to_version(row) for row in result.data]

    def get_version_by_id(self, version_id: int) -> Optional[ContentVersion]:
        """Get a specific version by ID."""
        result = (
            self.client.table("content_versions")
            .select("*")
            .eq("id", version_id)
            .execute()
        )

        if result.data:
            return self._row_to_version(result.data[0])
        return None

    def update_version_doc_id(self, version_id: int, doc_id: str) -> None:
        """Update the ElevenLabs doc_id for a version."""
        now = self._now_iso()
        self.client.table("content_versions").update(
            {"doc_id": doc_id, "pushed_at": now}
        ).eq("id", version_id).execute()

    # Content Drafts
    def create_draft(
        self,
        source_name: str,
        content: str,
        content_hash: str,
        diff_summary: Optional[str] = None,
        previous_version_id: Optional[int] = None,
    ) -> ContentDraft:
        """Create a new draft for review."""
        now = self._now_iso()

        # Expire any existing pending drafts for this source
        self.client.table("content_drafts").update({"status": "expired"}).eq(
            "source_name", source_name
        ).eq("status", "pending").execute()

        # Insert new draft
        data = {
            "source_name": source_name,
            "content": content,
            "content_hash": content_hash,
            "created_at": now,
            "status": "pending",
            "diff_summary": diff_summary,
            "previous_version_id": previous_version_id,
        }

        result = self.client.table("content_drafts").insert(data).execute()
        row = result.data[0]
        return self._row_to_draft(row)

    def get_pending_drafts(self, source_name: Optional[str] = None) -> list[ContentDraft]:
        """Get all pending drafts, optionally filtered by source."""
        query = (
            self.client.table("content_drafts")
            .select("*")
            .eq("status", "pending")
            .order("created_at", desc=True)
        )

        if source_name:
            query = query.eq("source_name", source_name)

        result = query.execute()
        return [self._row_to_draft(row) for row in result.data]

    def get_draft_by_id(self, draft_id: int) -> Optional[ContentDraft]:
        """Get a specific draft by ID."""
        result = (
            self.client.table("content_drafts").select("*").eq("id", draft_id).execute()
        )

        if result.data:
            return self._row_to_draft(result.data[0])
        return None

    def update_draft_status(self, draft_id: int, status: str) -> None:
        """Update draft status (approved, rejected, expired)."""
        self.client.table("content_drafts").update({"status": status}).eq(
            "id", draft_id
        ).execute()

    # Execution History
    def add_execution(
        self,
        source_name: str,
        status: str,
        content_hash: Optional[str] = None,
        doc_id: Optional[str] = None,
        error: Optional[str] = None,
        diff_summary: Optional[str] = None,
        version_id: Optional[int] = None,
    ) -> ExecutionRecord:
        """Add an execution record."""
        now = self._now_iso()

        data = {
            "source_name": source_name,
            "timestamp": now,
            "status": status,
            "content_hash": content_hash,
            "doc_id": doc_id,
            "error": error,
            "diff_summary": diff_summary,
            "version_id": version_id,
        }

        result = self.client.table("execution_history").insert(data).execute()
        row = result.data[0]
        return self._row_to_execution(row)

    def get_history(
        self,
        source_name: Optional[str] = None,
        limit: int = 100,
    ) -> list[ExecutionRecord]:
        """Get execution history."""
        query = (
            self.client.table("execution_history")
            .select("*")
            .order("timestamp", desc=True)
            .limit(limit)
        )

        if source_name:
            query = query.eq("source_name", source_name)

        result = query.execute()
        return [self._row_to_execution(row) for row in result.data]

    def get_last_execution(self, source_name: str) -> Optional[ExecutionRecord]:
        """Get the most recent execution for a source."""
        result = (
            self.client.table("execution_history")
            .select("*")
            .eq("source_name", source_name)
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
        )

        if result.data:
            return self._row_to_execution(result.data[0])
        return None

    # Cleanup
    def cleanup_old_versions(self, source_name: str, keep: int = 10) -> int:
        """Delete old versions, keeping the most recent N."""
        # Get IDs to keep
        result = (
            self.client.table("content_versions")
            .select("id")
            .eq("source_name", source_name)
            .order("created_at", desc=True)
            .limit(keep)
            .execute()
        )
        keep_ids = [row["id"] for row in result.data]

        if not keep_ids:
            return 0

        # Delete others (Supabase doesn't support NOT IN directly, so we use neq for each)
        # For simplicity, fetch all IDs and delete those not in keep_ids
        all_result = (
            self.client.table("content_versions")
            .select("id")
            .eq("source_name", source_name)
            .execute()
        )
        delete_ids = [row["id"] for row in all_result.data if row["id"] not in keep_ids]

        deleted_count = 0
        for del_id in delete_ids:
            self.client.table("content_versions").delete().eq("id", del_id).execute()
            deleted_count += 1

        return deleted_count

    def cleanup_old_drafts(self, days: int = 7) -> int:
        """Delete drafts older than N days that aren't pending."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        # Get drafts to delete
        result = (
            self.client.table("content_drafts")
            .select("id")
            .neq("status", "pending")
            .lt("created_at", cutoff)
            .execute()
        )

        deleted_count = 0
        for row in result.data:
            self.client.table("content_drafts").delete().eq("id", row["id"]).execute()
            deleted_count += 1

        return deleted_count

    # Metrics
    def save_metric(
        self,
        metric_name: str,
        metric_value: float,
        labels: Optional[dict] = None,
    ) -> MetricEvent:
        """Save a metric event to Supabase."""
        now = self._now_iso()

        data = {
            "timestamp": now,
            "metric_name": metric_name,
            "metric_value": metric_value,
            "labels": labels or {},
        }

        result = self.client.table("metrics_events").insert(data).execute()
        row = result.data[0]
        return self._row_to_metric(row)

    def get_metrics(
        self,
        metric_name: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        labels: Optional[dict] = None,
        limit: int = 1000,
    ) -> list[MetricEvent]:
        """Get metric events with optional filtering."""
        query = (
            self.client.table("metrics_events")
            .select("*")
            .order("timestamp", desc=True)
            .limit(limit)
        )

        if metric_name:
            query = query.eq("metric_name", metric_name)

        if start_time:
            query = query.gte("timestamp", start_time)

        if end_time:
            query = query.lte("timestamp", end_time)

        result = query.execute()

        metrics = []
        for row in result.data:
            metric = self._row_to_metric(row)
            # Filter by labels if specified
            if labels:
                if all(metric.labels.get(k) == v for k, v in labels.items()):
                    metrics.append(metric)
            else:
                metrics.append(metric)

        return metrics

    def get_metric_summary(
        self,
        metric_name: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        labels: Optional[dict] = None,
    ) -> dict:
        """Get summary statistics for a metric.

        Note: Supabase doesn't support aggregations directly,
        so we fetch all and compute in Python.
        """
        metrics = self.get_metrics(
            metric_name=metric_name,
            start_time=start_time,
            end_time=end_time,
            labels=labels,
            limit=10000,  # Higher limit for aggregation
        )

        if not metrics:
            return {
                "count": 0,
                "total": 0,
                "avg": 0,
                "min": 0,
                "max": 0,
            }

        values = [m.metric_value for m in metrics]
        return {
            "count": len(values),
            "total": sum(values),
            "avg": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
        }

    def cleanup_old_metrics(self, days: int = 30) -> int:
        """Delete metrics older than N days."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        # Get metrics to delete
        result = (
            self.client.table("metrics_events")
            .select("id")
            .lt("timestamp", cutoff)
            .execute()
        )

        deleted_count = 0
        for row in result.data:
            self.client.table("metrics_events").delete().eq("id", row["id"]).execute()
            deleted_count += 1

        return deleted_count
