"""Custom exception types for dynamic-kb."""


class DynamicKBError(Exception):
    """Base exception for dynamic-kb."""


class ScraperError(DynamicKBError):
    """Raised when web scraping fails."""


class AIProcessorError(DynamicKBError):
    """Raised when AI processing fails."""


class ElevenLabsError(DynamicKBError):
    """Raised when ElevenLabs API fails."""


class ConfigurationError(DynamicKBError):
    """Raised when configuration is invalid."""
