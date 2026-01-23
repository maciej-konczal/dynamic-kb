"""Shared test fixtures for Dynamic-KB."""

import tempfile
import shutil
from pathlib import Path

import pytest

from app.utils.database import Database
from app.utils.storage import Storage


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test data."""
    dir_path = tempfile.mkdtemp()
    yield dir_path
    shutil.rmtree(dir_path)


@pytest.fixture
def test_db(temp_dir):
    """Create a test database instance."""
    db_path = Path(temp_dir) / "test.db"
    return Database(str(db_path))


@pytest.fixture
def test_storage(temp_dir):
    """Create a test storage instance."""
    return Storage(data_dir=temp_dir)


@pytest.fixture
def sample_content():
    """Sample content for testing."""
    return """# Test Article

This is a test article about Dynamic-KB.

## Features
- Web scraping
- AI processing
- ElevenLabs integration

## Conclusion
Dynamic-KB is great!
"""


@pytest.fixture
def sample_content_v2():
    """Modified sample content for testing diffs."""
    return """# Test Article

This is a test article about Dynamic-KB.

## Features
- Web scraping
- AI processing
- ElevenLabs integration
- **New feature: Version history**

## Conclusion
Dynamic-KB is awesome!
"""


@pytest.fixture
def sample_source_config():
    """Sample source configuration dict."""
    return {
        "name": "Test Source",
        "url": "https://example.com/news",
        "enabled": True,
        "scraping": {
            "max_depth": 1,
            "max_pages": 5,
            "url_pattern": "^https://example\\.com/news",
        },
        "elevenlabs": {
            "agent_ids": ["agent_test123"],
            "kb_prefix": "TEST_KB",
        },
    }
