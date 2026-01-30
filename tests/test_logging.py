"""Tests for structured logging module."""

import logging
import os
from unittest.mock import patch

import pytest

from app.core.logging import get_logger, setup_logging


class TestGetLogger:
    """Test the get_logger function."""

    def test_returns_logger_instance(self):
        """get_logger should return a logging.Logger instance."""
        logger = get_logger("test_module")
        assert isinstance(logger, logging.Logger)

    def test_logger_name_prefix(self):
        """Logger name should have dynamic_kb prefix."""
        logger = get_logger("scraper")
        assert logger.name == "dynamic_kb.scraper"

    def test_different_modules_get_different_loggers(self):
        """Different module names should get different loggers."""
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")
        assert logger1.name != logger2.name
        assert logger1.name == "dynamic_kb.module1"
        assert logger2.name == "dynamic_kb.module2"

    def test_same_module_gets_same_logger(self):
        """Same module name should return same logger instance."""
        logger1 = get_logger("same_module")
        logger2 = get_logger("same_module")
        assert logger1 is logger2


class TestSetupLogging:
    """Test the setup_logging function."""

    @pytest.fixture(autouse=True)
    def reset_root_logger(self):
        """Reset root logger before each test."""
        root_logger = logging.getLogger()
        # Remove all handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        # Reset level
        root_logger.setLevel(logging.WARNING)
        yield

    def test_default_log_level_is_info(self):
        """Default log level should be INFO when LOG_LEVEL not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove LOG_LEVEL if it exists
            os.environ.pop("LOG_LEVEL", None)
            setup_logging()
            root_logger = logging.getLogger()
            assert root_logger.level == logging.INFO

    def test_log_level_from_environment(self):
        """Log level should be configurable via LOG_LEVEL env var."""
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            setup_logging()
            root_logger = logging.getLogger()
            assert root_logger.level == logging.DEBUG

    def test_log_level_case_insensitive(self):
        """LOG_LEVEL should be case insensitive."""
        with patch.dict(os.environ, {"LOG_LEVEL": "warning"}):
            setup_logging()
            root_logger = logging.getLogger()
            assert root_logger.level == logging.WARNING

    def test_invalid_log_level_defaults_to_info(self):
        """Invalid LOG_LEVEL should default to INFO."""
        with patch.dict(os.environ, {"LOG_LEVEL": "INVALID_LEVEL"}):
            setup_logging()
            root_logger = logging.getLogger()
            assert root_logger.level == logging.INFO


class TestLoggerOutput:
    """Test that loggers produce expected output."""

    def test_logger_logs_info_messages(self, caplog):
        """Logger should log INFO level messages."""
        with caplog.at_level(logging.INFO):
            logger = get_logger("test_info")
            logger.info("Test info message")

        assert "Test info message" in caplog.text

    def test_logger_logs_warning_messages(self, caplog):
        """Logger should log WARNING level messages."""
        with caplog.at_level(logging.WARNING):
            logger = get_logger("test_warning")
            logger.warning("Test warning message")

        assert "Test warning message" in caplog.text

    def test_logger_logs_error_messages(self, caplog):
        """Logger should log ERROR level messages."""
        with caplog.at_level(logging.ERROR):
            logger = get_logger("test_error")
            logger.error("Test error message")

        assert "Test error message" in caplog.text

    def test_logger_includes_module_name(self, caplog):
        """Log output should include the module name."""
        with caplog.at_level(logging.INFO):
            logger = get_logger("my_module")
            logger.info("Module test")

        assert "dynamic_kb.my_module" in caplog.text
