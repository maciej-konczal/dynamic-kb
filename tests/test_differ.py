"""Tests for app.core.differ module."""

import pytest
from app.core.differ import ContentDiffer, ContentVersion, DiffResult


class TestContentDiffer:
    """Test ContentDiffer class."""

    def test_compute_hash_deterministic(self):
        """Test that hash computation is deterministic."""
        content = "Test content for hashing"

        hash1 = ContentDiffer.compute_hash(content)
        hash2 = ContentDiffer.compute_hash(content)

        assert hash1 == hash2

    def test_compute_hash_different_content(self):
        """Test that different content produces different hashes."""
        hash1 = ContentDiffer.compute_hash("Content A")
        hash2 = ContentDiffer.compute_hash("Content B")

        assert hash1 != hash2

    def test_compute_hash_whitespace_sensitive(self):
        """Test that hashes are sensitive to whitespace."""
        hash1 = ContentDiffer.compute_hash("Hello World")
        hash2 = ContentDiffer.compute_hash("Hello  World")

        assert hash1 != hash2

    def test_create_version(self, sample_content):
        """Test creating a ContentVersion from content."""
        version = ContentDiffer.create_version(sample_content)

        assert version.hash == ContentDiffer.compute_hash(sample_content)
        assert version.timestamp is not None
        assert version.content_preview == sample_content[:500]

    def test_create_version_long_content(self):
        """Test that content preview is truncated."""
        long_content = "x" * 1000

        version = ContentDiffer.create_version(long_content)

        assert len(version.content_preview) == 500

    def test_compare_no_previous_version(self, sample_content):
        """Test comparison when there's no previous version."""
        differ = ContentDiffer()

        result = differ.compare(None, sample_content)

        assert result.has_changes is True
        assert result.old_hash is None
        assert result.new_hash is not None

    def test_compare_same_content(self, sample_content):
        """Test comparison when content is identical."""
        differ = ContentDiffer()
        old_version = ContentDiffer.create_version(sample_content)

        result = differ.compare(old_version, sample_content)

        assert result.has_changes is False
        assert result.old_hash == result.new_hash

    def test_compare_different_content(self, sample_content, sample_content_v2):
        """Test comparison when content is different."""
        differ = ContentDiffer()
        old_version = ContentDiffer.create_version(sample_content)

        result = differ.compare(old_version, sample_content_v2)

        assert result.has_changes is True
        assert result.old_hash != result.new_hash

    def test_generate_diff_summary_new_content(self, sample_content):
        """Test diff summary for new content."""
        differ = ContentDiffer()

        summary = differ.generate_diff_summary(None, sample_content)

        assert "New content" in summary

    def test_generate_diff_summary_changes(self, sample_content, sample_content_v2):
        """Test diff summary shows added/removed lines."""
        differ = ContentDiffer()

        summary = differ.generate_diff_summary(sample_content, sample_content_v2)

        assert "Added" in summary or "Removed" in summary

    def test_generate_diff_summary_no_changes(self, sample_content):
        """Test diff summary when no changes."""
        differ = ContentDiffer()

        summary = differ.generate_diff_summary(sample_content, sample_content)

        assert "No significant changes" in summary


class TestDiffResult:
    """Test DiffResult dataclass."""

    def test_diff_result_creation(self):
        """Test creating a DiffResult."""
        result = DiffResult(
            has_changes=True,
            old_hash="old123",
            new_hash="new456",
            old_timestamp="2024-01-01T00:00:00",
            new_timestamp="2024-01-02T00:00:00",
        )

        assert result.has_changes is True
        assert result.old_hash == "old123"
        assert result.new_hash == "new456"


class TestContentVersion:
    """Test ContentVersion dataclass."""

    def test_content_version_creation(self):
        """Test creating a ContentVersion."""
        version = ContentVersion(
            hash="abc123",
            timestamp="2024-01-01T00:00:00",
            content_preview="Test preview",
        )

        assert version.hash == "abc123"
        assert version.timestamp == "2024-01-01T00:00:00"
        assert version.content_preview == "Test preview"
