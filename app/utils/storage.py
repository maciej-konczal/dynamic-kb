"""File and state management utilities with SQLite backend."""

from datetime import datetime
from pathlib import Path
from typing import Optional

from app.utils.database import Database, ContentVersion, ContentDraft, ExecutionRecord


class Storage:
    """Handles file and state persistence using SQLite."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.outputs_dir = self.data_dir / "outputs"

        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self.db = Database(str(self.data_dir / "kb_sync.db"))

    # Content Versions
    def get_latest_version(self, source_name: str) -> Optional[ContentVersion]:
        """Get the most recent version for a source."""
        return self.db.get_latest_version(source_name)

    def get_versions(self, source_name: str, limit: int = 10) -> list[ContentVersion]:
        """Get version history for a source."""
        return self.db.get_versions(source_name, limit)

    def get_version_by_id(self, version_id: int) -> Optional[ContentVersion]:
        """Get a specific version by ID."""
        return self.db.get_version_by_id(version_id)

    def save_version(
        self,
        source_name: str,
        content: str,
        content_hash: str,
        doc_id: Optional[str] = None,
    ) -> ContentVersion:
        """Save a new content version."""
        return self.db.save_version(source_name, content, content_hash, doc_id)

    def update_version_doc_id(self, version_id: int, doc_id: str) -> None:
        """Update the ElevenLabs doc_id for a version."""
        self.db.update_version_doc_id(version_id, doc_id)

    # Content Drafts
    def create_draft(
        self,
        source_name: str,
        content: str,
        content_hash: str,
        diff_summary: Optional[str] = None,
    ) -> ContentDraft:
        """Create a new draft for review."""
        previous = self.get_latest_version(source_name)
        previous_id = previous.id if previous else None
        return self.db.create_draft(
            source_name, content, content_hash, diff_summary, previous_id
        )

    def get_pending_drafts(self, source_name: Optional[str] = None) -> list[ContentDraft]:
        """Get all pending drafts."""
        return self.db.get_pending_drafts(source_name)

    def get_draft_by_id(self, draft_id: int) -> Optional[ContentDraft]:
        """Get a specific draft by ID."""
        return self.db.get_draft_by_id(draft_id)

    def approve_draft(self, draft_id: int) -> Optional[ContentVersion]:
        """Approve a draft and convert it to a version."""
        draft = self.db.get_draft_by_id(draft_id)
        if not draft or draft.status != "pending":
            return None

        # Create version from draft
        version = self.save_version(
            draft.source_name,
            draft.content,
            draft.content_hash,
        )

        # Mark draft as approved
        self.db.update_draft_status(draft_id, "approved")

        return version

    def reject_draft(self, draft_id: int) -> bool:
        """Reject a draft."""
        draft = self.db.get_draft_by_id(draft_id)
        if not draft or draft.status != "pending":
            return False

        self.db.update_draft_status(draft_id, "rejected")
        return True

    # Execution History
    def get_history(
        self,
        source_name: Optional[str] = None,
        limit: int = 100,
    ) -> list[ExecutionRecord]:
        """Get execution history."""
        return self.db.get_history(source_name, limit)

    def get_last_execution(self, source_name: str) -> Optional[ExecutionRecord]:
        """Get the most recent execution for a source."""
        return self.db.get_last_execution(source_name)

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
        return self.db.add_execution(
            source_name, status, content_hash, doc_id, error, diff_summary, version_id
        )

    # Output file management (for backwards compatibility)
    def save_output(self, source_name: str, content: str, extension: str = "md") -> str:
        """Save output content to file and return the path."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in source_name)
        filename = f"{safe_name}_{timestamp}.{extension}"
        filepath = self.outputs_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return str(filepath)

    def get_output_content(self, filepath: str) -> Optional[str]:
        """Read content from an output file."""
        path = Path(filepath)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return None

    def list_outputs(self, source_name: Optional[str] = None) -> list[Path]:
        """List output files, optionally filtered by source name."""
        outputs = list(self.outputs_dir.glob("*.md"))
        if source_name:
            safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in source_name)
            outputs = [o for o in outputs if o.name.startswith(safe_name)]
        return sorted(outputs, key=lambda p: p.stat().st_mtime, reverse=True)

    # Cleanup
    def cleanup_old_versions(self, source_name: str, keep: int = 10) -> int:
        """Delete old versions, keeping the most recent N."""
        return self.db.cleanup_old_versions(source_name, keep)

    def cleanup_old_drafts(self, days: int = 7) -> int:
        """Delete drafts older than N days that aren't pending."""
        return self.db.cleanup_old_drafts(days)
