"""SQLite database for content storage and versioning."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable
from dataclasses import dataclass


@dataclass
class ContentVersion:
    """A stored version of content."""

    id: int
    source_name: str
    content: str
    content_hash: str
    created_at: str
    doc_id: Optional[str] = None  # ElevenLabs document ID if pushed
    pushed_at: Optional[str] = None
    version_number: int = 1


@dataclass
class ContentDraft:
    """A draft awaiting approval before push."""

    id: int
    source_name: str
    content: str
    content_hash: str
    created_at: str
    status: str  # "pending", "approved", "rejected", "expired"
    diff_summary: Optional[str] = None
    previous_version_id: Optional[int] = None


@dataclass
class ExecutionRecord:
    """Record of a single execution run."""

    id: int
    source_name: str
    timestamp: str
    status: str  # "success", "failed", "no_changes", "draft_created"
    content_hash: Optional[str] = None
    doc_id: Optional[str] = None
    error: Optional[str] = None
    diff_summary: Optional[str] = None
    version_id: Optional[int] = None


@dataclass
class MetricEvent:
    """A single metric event for persistence."""

    id: int
    timestamp: str
    metric_name: str
    metric_value: float
    labels: dict  # JSON object with label key-values


@runtime_checkable
class DatabaseProtocol(Protocol):
    """Protocol defining the database interface."""

    def save_version(
        self,
        source_name: str,
        content: str,
        content_hash: str,
        doc_id: Optional[str] = None,
    ) -> ContentVersion: ...

    def get_latest_version(self, source_name: str) -> Optional[ContentVersion]: ...

    def get_versions(self, source_name: str, limit: int = 10) -> list[ContentVersion]: ...

    def get_version_by_id(self, version_id: int) -> Optional[ContentVersion]: ...

    def update_version_doc_id(self, version_id: int, doc_id: str) -> None: ...

    def create_draft(
        self,
        source_name: str,
        content: str,
        content_hash: str,
        diff_summary: Optional[str] = None,
        previous_version_id: Optional[int] = None,
    ) -> ContentDraft: ...

    def get_pending_drafts(self, source_name: Optional[str] = None) -> list[ContentDraft]: ...

    def get_draft_by_id(self, draft_id: int) -> Optional[ContentDraft]: ...

    def update_draft_status(self, draft_id: int, status: str) -> None: ...

    def add_execution(
        self,
        source_name: str,
        status: str,
        content_hash: Optional[str] = None,
        doc_id: Optional[str] = None,
        error: Optional[str] = None,
        diff_summary: Optional[str] = None,
        version_id: Optional[int] = None,
    ) -> ExecutionRecord: ...

    def get_history(
        self,
        source_name: Optional[str] = None,
        limit: int = 100,
    ) -> list[ExecutionRecord]: ...

    def get_last_execution(self, source_name: str) -> Optional[ExecutionRecord]: ...

    def cleanup_old_versions(self, source_name: str, keep: int = 10) -> int: ...

    def cleanup_old_drafts(self, days: int = 7) -> int: ...

    # Metrics
    def save_metric(
        self,
        metric_name: str,
        metric_value: float,
        labels: Optional[dict] = None,
    ) -> MetricEvent: ...

    def get_metrics(
        self,
        metric_name: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        labels: Optional[dict] = None,
        limit: int = 1000,
    ) -> list[MetricEvent]: ...

    def get_metric_summary(
        self,
        metric_name: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        labels: Optional[dict] = None,
    ) -> dict: ...

    def cleanup_old_metrics(self, days: int = 30) -> int: ...


class Database:
    """SQLite database manager for dynamic-kb."""

    def __init__(self, db_path: str = "data/kb_sync.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_conn(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        """Initialize database schema."""
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS content_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    doc_id TEXT,
                    pushed_at TEXT,
                    version_number INTEGER DEFAULT 1,
                    UNIQUE(source_name, content_hash)
                );

                CREATE TABLE IF NOT EXISTS content_drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    diff_summary TEXT,
                    previous_version_id INTEGER,
                    FOREIGN KEY (previous_version_id) REFERENCES content_versions(id)
                );

                CREATE TABLE IF NOT EXISTS execution_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_name TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    status TEXT NOT NULL,
                    content_hash TEXT,
                    doc_id TEXT,
                    error TEXT,
                    diff_summary TEXT,
                    version_id INTEGER,
                    FOREIGN KEY (version_id) REFERENCES content_versions(id)
                );

                CREATE INDEX IF NOT EXISTS idx_versions_source ON content_versions(source_name);
                CREATE INDEX IF NOT EXISTS idx_drafts_source ON content_drafts(source_name);
                CREATE INDEX IF NOT EXISTS idx_drafts_status ON content_drafts(status);
                CREATE INDEX IF NOT EXISTS idx_history_source ON execution_history(source_name);

                CREATE TABLE IF NOT EXISTS metrics_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    labels TEXT DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics_events(metric_name);
                CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics_events(timestamp);
            """)

    # Content Versions
    def save_version(
        self,
        source_name: str,
        content: str,
        content_hash: str,
        doc_id: Optional[str] = None,
    ) -> ContentVersion:
        """Save a new content version."""
        now = datetime.now().isoformat()

        # Get next version number
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT MAX(version_number) FROM content_versions WHERE source_name = ?",
                (source_name,)
            ).fetchone()
            version_number = (row[0] or 0) + 1

            cursor = conn.execute(
                """INSERT INTO content_versions
                   (source_name, content, content_hash, created_at, doc_id, pushed_at, version_number)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source_name, content_hash) DO UPDATE SET
                   doc_id = excluded.doc_id,
                   pushed_at = excluded.pushed_at""",
                (source_name, content, content_hash, now, doc_id, now if doc_id else None, version_number)
            )

            return ContentVersion(
                id=cursor.lastrowid,
                source_name=source_name,
                content=content,
                content_hash=content_hash,
                created_at=now,
                doc_id=doc_id,
                pushed_at=now if doc_id else None,
                version_number=version_number,
            )

    def get_latest_version(self, source_name: str) -> Optional[ContentVersion]:
        """Get the most recent version for a source."""
        with self._get_conn() as conn:
            row = conn.execute(
                """SELECT * FROM content_versions
                   WHERE source_name = ?
                   ORDER BY created_at DESC LIMIT 1""",
                (source_name,)
            ).fetchone()

            if row:
                return ContentVersion(**dict(row))
            return None

    def get_versions(self, source_name: str, limit: int = 10) -> list[ContentVersion]:
        """Get version history for a source."""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM content_versions
                   WHERE source_name = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (source_name, limit)
            ).fetchall()

            return [ContentVersion(**dict(row)) for row in rows]

    def get_version_by_id(self, version_id: int) -> Optional[ContentVersion]:
        """Get a specific version by ID."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM content_versions WHERE id = ?",
                (version_id,)
            ).fetchone()

            if row:
                return ContentVersion(**dict(row))
            return None

    def update_version_doc_id(self, version_id: int, doc_id: str) -> None:
        """Update the ElevenLabs doc_id for a version."""
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE content_versions SET doc_id = ?, pushed_at = ? WHERE id = ?",
                (doc_id, now, version_id)
            )

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
        now = datetime.now().isoformat()

        # Expire any existing pending drafts for this source
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE content_drafts SET status = 'expired' WHERE source_name = ? AND status = 'pending'",
                (source_name,)
            )

            cursor = conn.execute(
                """INSERT INTO content_drafts
                   (source_name, content, content_hash, created_at, status, diff_summary, previous_version_id)
                   VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
                (source_name, content, content_hash, now, diff_summary, previous_version_id)
            )

            return ContentDraft(
                id=cursor.lastrowid,
                source_name=source_name,
                content=content,
                content_hash=content_hash,
                created_at=now,
                status="pending",
                diff_summary=diff_summary,
                previous_version_id=previous_version_id,
            )

    def get_pending_drafts(self, source_name: Optional[str] = None) -> list[ContentDraft]:
        """Get all pending drafts, optionally filtered by source."""
        with self._get_conn() as conn:
            if source_name:
                rows = conn.execute(
                    "SELECT * FROM content_drafts WHERE status = 'pending' AND source_name = ? ORDER BY created_at DESC",
                    (source_name,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM content_drafts WHERE status = 'pending' ORDER BY created_at DESC"
                ).fetchall()

            return [ContentDraft(**dict(row)) for row in rows]

    def get_draft_by_id(self, draft_id: int) -> Optional[ContentDraft]:
        """Get a specific draft by ID."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM content_drafts WHERE id = ?",
                (draft_id,)
            ).fetchone()

            if row:
                return ContentDraft(**dict(row))
            return None

    def update_draft_status(self, draft_id: int, status: str) -> None:
        """Update draft status (approved, rejected, expired)."""
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE content_drafts SET status = ? WHERE id = ?",
                (status, draft_id)
            )

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
        now = datetime.now().isoformat()

        with self._get_conn() as conn:
            cursor = conn.execute(
                """INSERT INTO execution_history
                   (source_name, timestamp, status, content_hash, doc_id, error, diff_summary, version_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (source_name, now, status, content_hash, doc_id, error, diff_summary, version_id)
            )

            return ExecutionRecord(
                id=cursor.lastrowid,
                source_name=source_name,
                timestamp=now,
                status=status,
                content_hash=content_hash,
                doc_id=doc_id,
                error=error,
                diff_summary=diff_summary,
                version_id=version_id,
            )

    def get_history(
        self,
        source_name: Optional[str] = None,
        limit: int = 100,
    ) -> list[ExecutionRecord]:
        """Get execution history."""
        with self._get_conn() as conn:
            if source_name:
                rows = conn.execute(
                    """SELECT * FROM execution_history
                       WHERE source_name = ?
                       ORDER BY timestamp DESC LIMIT ?""",
                    (source_name, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM execution_history ORDER BY timestamp DESC LIMIT ?",
                    (limit,)
                ).fetchall()

            return [ExecutionRecord(**dict(row)) for row in rows]

    def get_last_execution(self, source_name: str) -> Optional[ExecutionRecord]:
        """Get the most recent execution for a source."""
        with self._get_conn() as conn:
            row = conn.execute(
                """SELECT * FROM execution_history
                   WHERE source_name = ?
                   ORDER BY timestamp DESC LIMIT 1""",
                (source_name,)
            ).fetchone()

            if row:
                return ExecutionRecord(**dict(row))
            return None

    # Cleanup
    def cleanup_old_versions(self, source_name: str, keep: int = 10) -> int:
        """Delete old versions, keeping the most recent N."""
        with self._get_conn() as conn:
            # Get IDs to keep
            keep_ids = conn.execute(
                """SELECT id FROM content_versions
                   WHERE source_name = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (source_name, keep)
            ).fetchall()
            keep_ids = [row[0] for row in keep_ids]

            if not keep_ids:
                return 0

            # Delete others
            cursor = conn.execute(
                f"""DELETE FROM content_versions
                    WHERE source_name = ? AND id NOT IN ({','.join('?' * len(keep_ids))})""",
                (source_name, *keep_ids)
            )
            return cursor.rowcount

    def cleanup_old_drafts(self, days: int = 7) -> int:
        """Delete drafts older than N days that aren't pending."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                """DELETE FROM content_drafts
                   WHERE status != 'pending'
                   AND datetime(created_at) < datetime('now', ?)""",
                (f'-{days} days',)
            )
            return cursor.rowcount

    # Metrics
    def save_metric(
        self,
        metric_name: str,
        metric_value: float,
        labels: Optional[dict] = None,
    ) -> MetricEvent:
        """Save a metric event."""
        now = datetime.now(timezone.utc).isoformat()
        labels_json = json.dumps(labels or {})

        with self._get_conn() as conn:
            cursor = conn.execute(
                """INSERT INTO metrics_events (timestamp, metric_name, metric_value, labels)
                   VALUES (?, ?, ?, ?)""",
                (now, metric_name, metric_value, labels_json)
            )

            return MetricEvent(
                id=cursor.lastrowid,
                timestamp=now,
                metric_name=metric_name,
                metric_value=metric_value,
                labels=labels or {},
            )

    def get_metrics(
        self,
        metric_name: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        labels: Optional[dict] = None,
        limit: int = 1000,
    ) -> list[MetricEvent]:
        """Get metric events with optional filtering."""
        with self._get_conn() as conn:
            query = "SELECT * FROM metrics_events WHERE 1=1"
            params = []

            if metric_name:
                query += " AND metric_name = ?"
                params.append(metric_name)

            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)

            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()

            results = []
            for row in rows:
                row_dict = dict(row)
                row_dict["labels"] = json.loads(row_dict.get("labels", "{}"))
                # Filter by labels if specified
                if labels:
                    if all(row_dict["labels"].get(k) == v for k, v in labels.items()):
                        results.append(MetricEvent(**row_dict))
                else:
                    results.append(MetricEvent(**row_dict))

            return results

    def get_metric_summary(
        self,
        metric_name: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        labels: Optional[dict] = None,
    ) -> dict:
        """Get summary statistics for a metric."""
        with self._get_conn() as conn:
            query = """
                SELECT
                    COUNT(*) as count,
                    SUM(metric_value) as total,
                    AVG(metric_value) as avg,
                    MIN(metric_value) as min,
                    MAX(metric_value) as max
                FROM metrics_events
                WHERE metric_name = ?
            """
            params = [metric_name]

            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)

            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)

            row = conn.execute(query, params).fetchone()

            return {
                "count": row["count"] or 0,
                "total": row["total"] or 0,
                "avg": row["avg"] or 0,
                "min": row["min"] or 0,
                "max": row["max"] or 0,
            }

    def cleanup_old_metrics(self, days: int = 30) -> int:
        """Delete metrics older than N days."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                """DELETE FROM metrics_events
                   WHERE datetime(timestamp) < datetime('now', ?)""",
                (f'-{days} days',)
            )
            return cursor.rowcount
