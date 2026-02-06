"""Pytest configuration and fixtures."""

import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def reset_logging():
    """Reset logging configuration between tests."""
    import logging

    # Store original level
    root_logger = logging.getLogger()
    original_level = root_logger.level

    yield

    # Restore original level
    root_logger.setLevel(original_level)


@pytest.fixture
def test_db():
    """Create a temporary database for testing."""
    from app.utils.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = Database(db_path)
        yield db


@pytest.fixture
def sample_content():
    """Sample markdown content for testing."""
    return """# Test Document

This is test content for the knowledge base.

## Section 1

Some information here.

## Section 2

More information here.
"""


@pytest.fixture
def sample_content_v2():
    """Sample markdown content v2 for testing version updates."""
    return """# Test Document (Updated)

This is updated test content for the knowledge base.

## Section 1

Updated information here.

## Section 2

More updated information here.

## Section 3 (New)

This section is new.
"""


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing.

    Clears Supabase env vars to ensure tests use SQLite.
    """
    # Save and clear Supabase env vars to force SQLite usage
    saved_url = os.environ.pop("SUPABASE_URL", None)
    saved_key = os.environ.pop("SUPABASE_KEY", None)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    finally:
        # Restore env vars
        if saved_url:
            os.environ["SUPABASE_URL"] = saved_url
        if saved_key:
            os.environ["SUPABASE_KEY"] = saved_key


@pytest.fixture
def test_storage(temp_dir):
    """Create a Storage instance for testing.

    Uses temp_dir which already clears Supabase env vars.
    """
    from app.utils.storage import Storage

    storage = Storage(data_dir=temp_dir)
    yield storage


@pytest.fixture
def sample_source_config():
    """Sample source configuration for testing."""
    return {
        "name": "Test Source",
        "url": "https://example.com",
        "enabled": True,
        "schedule": "0 8 * * *",
        "schedule_enabled": True,
        "scraping": {
            "max_depth": 1,
            "max_pages": 5,
            "capture_screenshots": True,
        },
        "prompts": {},
        "elevenlabs": {
            "kb_prefix": "TEST_KB",
            "agent_ids": ["agent1"],
        },
    }
