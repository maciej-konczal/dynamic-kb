"""Content change detection and versioning module."""

import hashlib
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ContentVersion:
    """Represents a version of content."""

    hash: str
    timestamp: str
    content_preview: str = ""  # First 500 chars for reference


@dataclass
class DiffResult:
    """Result of a content comparison."""

    has_changes: bool
    old_hash: Optional[str] = None
    new_hash: Optional[str] = None
    old_timestamp: Optional[str] = None
    new_timestamp: Optional[str] = None


class ContentDiffer:
    """Handles content hashing, comparison, and version tracking."""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path("data/content_hashes.json")

    @staticmethod
    def compute_hash(content: str) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def create_version(content: str) -> ContentVersion:
        """Create a ContentVersion from content string."""
        return ContentVersion(
            hash=ContentDiffer.compute_hash(content),
            timestamp=datetime.now().isoformat(),
            content_preview=content[:500],
        )

    def compare(
        self,
        old_version: Optional[ContentVersion],
        new_content: str,
    ) -> DiffResult:
        """Compare old version with new content."""
        new_hash = self.compute_hash(new_content)
        new_timestamp = datetime.now().isoformat()

        if old_version is None:
            return DiffResult(
                has_changes=True,
                old_hash=None,
                new_hash=new_hash,
                old_timestamp=None,
                new_timestamp=new_timestamp,
            )

        return DiffResult(
            has_changes=old_version.hash != new_hash,
            old_hash=old_version.hash,
            new_hash=new_hash,
            old_timestamp=old_version.timestamp,
            new_timestamp=new_timestamp,
        )

    def generate_diff_summary(
        self,
        old_content: Optional[str],
        new_content: str,
    ) -> str:
        """Generate a human-readable diff summary."""
        if old_content is None:
            return "New content (no previous version)"

        old_lines = set(old_content.split("\n"))
        new_lines = set(new_content.split("\n"))

        added = new_lines - old_lines
        removed = old_lines - new_lines

        summary_parts = []
        if added:
            summary_parts.append(f"Added {len(added)} lines")
        if removed:
            summary_parts.append(f"Removed {len(removed)} lines")

        if not summary_parts:
            return "No significant changes detected"

        return "; ".join(summary_parts)
