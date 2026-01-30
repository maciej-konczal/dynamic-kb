"""Tests for custom exception types."""

import pytest

from app.core.exceptions import (
    DynamicKBError,
    ScraperError,
    AIProcessorError,
    ElevenLabsError,
    ConfigurationError,
)


class TestExceptionHierarchy:
    """Test that exceptions follow the expected hierarchy."""

    def test_scraper_error_is_dynamic_kb_error(self):
        """ScraperError should be a subclass of DynamicKBError."""
        assert issubclass(ScraperError, DynamicKBError)

    def test_ai_processor_error_is_dynamic_kb_error(self):
        """AIProcessorError should be a subclass of DynamicKBError."""
        assert issubclass(AIProcessorError, DynamicKBError)

    def test_elevenlabs_error_is_dynamic_kb_error(self):
        """ElevenLabsError should be a subclass of DynamicKBError."""
        assert issubclass(ElevenLabsError, DynamicKBError)

    def test_configuration_error_is_dynamic_kb_error(self):
        """ConfigurationError should be a subclass of DynamicKBError."""
        assert issubclass(ConfigurationError, DynamicKBError)

    def test_dynamic_kb_error_is_exception(self):
        """DynamicKBError should be a subclass of Exception."""
        assert issubclass(DynamicKBError, Exception)


class TestExceptionMessages:
    """Test that exceptions preserve their messages."""

    def test_scraper_error_message(self):
        """ScraperError should preserve error message."""
        error = ScraperError("Failed to crawl URL")
        assert str(error) == "Failed to crawl URL"

    def test_ai_processor_error_message(self):
        """AIProcessorError should preserve error message."""
        error = AIProcessorError("Gemini API error")
        assert str(error) == "Gemini API error"

    def test_elevenlabs_error_message(self):
        """ElevenLabsError should preserve error message."""
        error = ElevenLabsError("API rate limit exceeded")
        assert str(error) == "API rate limit exceeded"

    def test_configuration_error_message(self):
        """ConfigurationError should preserve error message."""
        error = ConfigurationError("Invalid config.yaml")
        assert str(error) == "Invalid config.yaml"


class TestExceptionCatching:
    """Test that exceptions can be caught at different levels."""

    def test_catch_scraper_error_as_dynamic_kb_error(self):
        """Should be able to catch ScraperError as DynamicKBError."""
        with pytest.raises(DynamicKBError):
            raise ScraperError("test")

    def test_catch_ai_processor_error_as_dynamic_kb_error(self):
        """Should be able to catch AIProcessorError as DynamicKBError."""
        with pytest.raises(DynamicKBError):
            raise AIProcessorError("test")

    def test_catch_elevenlabs_error_as_dynamic_kb_error(self):
        """Should be able to catch ElevenLabsError as DynamicKBError."""
        with pytest.raises(DynamicKBError):
            raise ElevenLabsError("test")

    def test_catch_specific_error_type(self):
        """Should be able to catch specific error types."""
        with pytest.raises(ScraperError):
            raise ScraperError("test")

        with pytest.raises(AIProcessorError):
            raise AIProcessorError("test")

        with pytest.raises(ElevenLabsError):
            raise ElevenLabsError("test")

    def test_catch_all_dynamic_kb_errors(self):
        """Should be able to catch all errors with base class."""
        errors = [
            ScraperError("scraper"),
            AIProcessorError("ai"),
            ElevenLabsError("elevenlabs"),
            ConfigurationError("config"),
        ]

        for error in errors:
            try:
                raise error
            except DynamicKBError as e:
                assert str(e) in ["scraper", "ai", "elevenlabs", "config"]
