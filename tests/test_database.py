"""Tests for app.utils.database module."""

import pytest
from app.utils.database import Database, ContentVersion, ContentDraft, ExecutionRecord


class TestDatabase:
    """Test Database class."""

    def test_init_creates_tables(self, test_db):
        """Test that database initialization creates required tables."""
        with test_db._get_conn() as conn:
            # Check tables exist
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = [t[0] for t in tables]

            assert "content_versions" in table_names
            assert "content_drafts" in table_names
            assert "execution_history" in table_names

    def test_save_version(self, test_db, sample_content):
        """Test saving a content version."""
        version = test_db.save_version(
            source_name="Test Source",
            content=sample_content,
            content_hash="abc123",
            doc_id=None,
        )

        assert version.id is not None
        assert version.source_name == "Test Source"
        assert version.content == sample_content
        assert version.content_hash == "abc123"
        assert version.version_number == 1

    def test_save_version_increments_version_number(self, test_db, sample_content, sample_content_v2):
        """Test that version numbers increment for same source."""
        v1 = test_db.save_version("Test Source", sample_content, "hash1")
        v2 = test_db.save_version("Test Source", sample_content_v2, "hash2")

        assert v1.version_number == 1
        assert v2.version_number == 2

    def test_get_latest_version(self, test_db, sample_content, sample_content_v2):
        """Test retrieving the latest version."""
        test_db.save_version("Test Source", sample_content, "hash1")
        test_db.save_version("Test Source", sample_content_v2, "hash2")

        latest = test_db.get_latest_version("Test Source")

        assert latest is not None
        assert latest.content_hash == "hash2"
        assert latest.version_number == 2

    def test_get_latest_version_nonexistent(self, test_db):
        """Test getting latest version for nonexistent source."""
        result = test_db.get_latest_version("Nonexistent")
        assert result is None

    def test_get_versions(self, test_db, sample_content):
        """Test retrieving version history."""
        for i in range(5):
            test_db.save_version("Test Source", f"Content {i}", f"hash{i}")

        versions = test_db.get_versions("Test Source", limit=3)

        assert len(versions) == 3
        # Should be in reverse chronological order
        assert versions[0].version_number == 5
        assert versions[2].version_number == 3

    def test_get_version_by_id(self, test_db, sample_content):
        """Test retrieving a specific version by ID."""
        saved = test_db.save_version("Test Source", sample_content, "hash123")

        retrieved = test_db.get_version_by_id(saved.id)

        assert retrieved is not None
        assert retrieved.content == sample_content

    def test_update_version_doc_id(self, test_db, sample_content):
        """Test updating doc_id after ElevenLabs push."""
        version = test_db.save_version("Test Source", sample_content, "hash123")
        assert version.doc_id is None

        test_db.update_version_doc_id(version.id, "doc_elevenlabs_123")

        updated = test_db.get_version_by_id(version.id)
        assert updated.doc_id == "doc_elevenlabs_123"
        assert updated.pushed_at is not None


class TestContentDrafts:
    """Test content draft functionality."""

    def test_create_draft(self, test_db, sample_content):
        """Test creating a draft."""
        draft = test_db.create_draft(
            source_name="Test Source",
            content=sample_content,
            content_hash="hash123",
            diff_summary="New content",
        )

        assert draft.id is not None
        assert draft.source_name == "Test Source"
        assert draft.status == "pending"
        assert draft.diff_summary == "New content"

    def test_get_pending_drafts(self, test_db, sample_content):
        """Test retrieving pending drafts."""
        test_db.create_draft("Source 1", "Content 1", "hash1")
        test_db.create_draft("Source 2", "Content 2", "hash2")

        drafts = test_db.get_pending_drafts()

        assert len(drafts) == 2

    def test_get_pending_drafts_filtered(self, test_db, sample_content):
        """Test retrieving pending drafts filtered by source."""
        test_db.create_draft("Source 1", "Content 1", "hash1")
        test_db.create_draft("Source 2", "Content 2", "hash2")

        drafts = test_db.get_pending_drafts(source_name="Source 1")

        assert len(drafts) == 1
        assert drafts[0].source_name == "Source 1"

    def test_create_draft_expires_old_pending(self, test_db, sample_content):
        """Test that creating new draft expires old pending drafts for same source."""
        draft1 = test_db.create_draft("Test Source", "Content 1", "hash1")
        draft2 = test_db.create_draft("Test Source", "Content 2", "hash2")

        # Check first draft is expired
        old_draft = test_db.get_draft_by_id(draft1.id)
        assert old_draft.status == "expired"

        # Check second draft is pending
        new_draft = test_db.get_draft_by_id(draft2.id)
        assert new_draft.status == "pending"

    def test_update_draft_status(self, test_db, sample_content):
        """Test updating draft status."""
        draft = test_db.create_draft("Test Source", sample_content, "hash123")

        test_db.update_draft_status(draft.id, "approved")

        updated = test_db.get_draft_by_id(draft.id)
        assert updated.status == "approved"


class TestExecutionHistory:
    """Test execution history functionality."""

    def test_add_execution(self, test_db):
        """Test adding an execution record."""
        record = test_db.add_execution(
            source_name="Test Source",
            status="success",
            content_hash="hash123",
            doc_id="doc_123",
        )

        assert record.id is not None
        assert record.source_name == "Test Source"
        assert record.status == "success"

    def test_get_history(self, test_db):
        """Test retrieving execution history."""
        test_db.add_execution("Source 1", "success")
        test_db.add_execution("Source 2", "failed", error="Connection error")
        test_db.add_execution("Source 1", "no_changes")

        history = test_db.get_history()

        assert len(history) == 3

    def test_get_history_filtered(self, test_db):
        """Test retrieving execution history filtered by source."""
        test_db.add_execution("Source 1", "success")
        test_db.add_execution("Source 2", "failed")
        test_db.add_execution("Source 1", "success")

        history = test_db.get_history(source_name="Source 1")

        assert len(history) == 2
        assert all(h.source_name == "Source 1" for h in history)

    def test_get_last_execution(self, test_db):
        """Test getting the most recent execution."""
        test_db.add_execution("Test Source", "failed")
        test_db.add_execution("Test Source", "success")

        last = test_db.get_last_execution("Test Source")

        assert last is not None
        assert last.status == "success"


class TestCleanup:
    """Test cleanup functionality."""

    def test_cleanup_old_versions(self, test_db):
        """Test cleaning up old versions."""
        for i in range(15):
            test_db.save_version("Test Source", f"Content {i}", f"hash{i}")

        deleted = test_db.cleanup_old_versions("Test Source", keep=5)

        assert deleted == 10
        remaining = test_db.get_versions("Test Source", limit=100)
        assert len(remaining) == 5
