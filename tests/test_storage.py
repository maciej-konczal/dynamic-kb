"""Tests for app.utils.storage module."""

import pytest
from pathlib import Path

from app.utils.storage import Storage


class TestStorage:
    """Test Storage class."""

    def test_init_creates_directories(self, temp_dir):
        """Test that initialization creates required directories."""
        storage = Storage(data_dir=temp_dir)

        assert Path(temp_dir).exists()
        assert (Path(temp_dir) / "outputs").exists()

    def test_init_creates_database(self, temp_dir):
        """Test that initialization creates database."""
        storage = Storage(data_dir=temp_dir)

        assert (Path(temp_dir) / "kb_sync.db").exists()


class TestStorageVersions:
    """Test version management in Storage."""

    def test_save_and_get_version(self, test_storage, sample_content):
        """Test saving and retrieving a version."""
        version = test_storage.save_version(
            source_name="Test Source",
            content=sample_content,
            content_hash="hash123",
        )

        retrieved = test_storage.get_latest_version("Test Source")

        assert retrieved is not None
        assert retrieved.content == sample_content
        assert retrieved.content_hash == "hash123"

    def test_get_versions_list(self, test_storage, sample_content, sample_content_v2):
        """Test getting version history."""
        test_storage.save_version("Test Source", sample_content, "hash1")
        test_storage.save_version("Test Source", sample_content_v2, "hash2")

        versions = test_storage.get_versions("Test Source")

        assert len(versions) == 2

    def test_update_version_doc_id(self, test_storage, sample_content):
        """Test updating doc_id after push."""
        version = test_storage.save_version("Test Source", sample_content, "hash123")

        test_storage.update_version_doc_id(version.id, "doc_xyz")

        updated = test_storage.get_version_by_id(version.id)
        assert updated.doc_id == "doc_xyz"


class TestStorageDrafts:
    """Test draft management in Storage."""

    def test_create_draft(self, test_storage, sample_content):
        """Test creating a draft."""
        draft = test_storage.create_draft(
            source_name="Test Source",
            content=sample_content,
            content_hash="hash123",
            diff_summary="New content",
        )

        assert draft.id is not None
        assert draft.status == "pending"

    def test_get_pending_drafts(self, test_storage, sample_content):
        """Test retrieving pending drafts."""
        test_storage.create_draft("Source 1", "Content 1", "hash1")
        test_storage.create_draft("Source 2", "Content 2", "hash2")

        drafts = test_storage.get_pending_drafts()

        assert len(drafts) == 2

    def test_approve_draft(self, test_storage, sample_content):
        """Test approving a draft creates a version."""
        draft = test_storage.create_draft("Test Source", sample_content, "hash123")

        version = test_storage.approve_draft(draft.id)

        assert version is not None
        assert version.content == sample_content

        # Draft should be approved
        updated_draft = test_storage.get_draft_by_id(draft.id)
        assert updated_draft.status == "approved"

    def test_reject_draft(self, test_storage, sample_content):
        """Test rejecting a draft."""
        draft = test_storage.create_draft("Test Source", sample_content, "hash123")

        result = test_storage.reject_draft(draft.id)

        assert result is True
        updated = test_storage.get_draft_by_id(draft.id)
        assert updated.status == "rejected"

    def test_approve_nonexistent_draft(self, test_storage):
        """Test approving a nonexistent draft returns None."""
        result = test_storage.approve_draft(99999)
        assert result is None

    def test_draft_links_to_previous_version(self, test_storage, sample_content, sample_content_v2):
        """Test that draft links to previous version."""
        # Create initial version
        test_storage.save_version("Test Source", sample_content, "hash1")

        # Create draft
        draft = test_storage.create_draft("Test Source", sample_content_v2, "hash2")

        assert draft.previous_version_id is not None


class TestStorageHistory:
    """Test execution history in Storage."""

    def test_add_execution(self, test_storage):
        """Test adding an execution record."""
        record = test_storage.add_execution(
            source_name="Test Source",
            status="success",
            content_hash="hash123",
        )

        assert record.id is not None
        assert record.status == "success"

    def test_get_history(self, test_storage):
        """Test retrieving execution history."""
        test_storage.add_execution("Source 1", "success")
        test_storage.add_execution("Source 2", "failed")

        history = test_storage.get_history()

        assert len(history) == 2

    def test_get_last_execution(self, test_storage):
        """Test getting the most recent execution."""
        test_storage.add_execution("Test Source", "failed")
        test_storage.add_execution("Test Source", "success")

        last = test_storage.get_last_execution("Test Source")

        assert last.status == "success"


class TestStorageOutputs:
    """Test output file management in Storage."""

    def test_save_output(self, test_storage, sample_content):
        """Test saving output file."""
        filepath = test_storage.save_output("Test Source", sample_content)

        assert Path(filepath).exists()
        assert filepath.endswith(".md")

    def test_get_output_content(self, test_storage, sample_content):
        """Test reading output file content."""
        filepath = test_storage.save_output("Test Source", sample_content)

        content = test_storage.get_output_content(filepath)

        assert content == sample_content

    def test_list_outputs(self, test_storage, sample_content):
        """Test listing output files."""
        import time
        test_storage.save_output("Test Source", sample_content)
        time.sleep(0.01)  # Ensure different timestamps
        test_storage.save_output("Test Source", sample_content + " v2")

        outputs = test_storage.list_outputs("Test Source")

        assert len(outputs) >= 1  # At least one output

    def test_list_outputs_filtered(self, test_storage, sample_content):
        """Test listing outputs filtered by source."""
        test_storage.save_output("Source A", "Content A")
        test_storage.save_output("Source B", "Content B")

        outputs_a = test_storage.list_outputs("Source A")
        outputs_b = test_storage.list_outputs("Source B")

        assert len(outputs_a) == 1
        assert len(outputs_b) == 1


class TestStorageCleanup:
    """Test cleanup functionality in Storage."""

    def test_cleanup_old_versions(self, test_storage):
        """Test cleaning up old versions."""
        for i in range(10):
            test_storage.save_version("Test Source", f"Content {i}", f"hash{i}")

        deleted = test_storage.cleanup_old_versions("Test Source", keep=3)

        assert deleted == 7
        remaining = test_storage.get_versions("Test Source", limit=100)
        assert len(remaining) == 3
