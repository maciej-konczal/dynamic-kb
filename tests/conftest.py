"""Pytest configuration and fixtures."""

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
