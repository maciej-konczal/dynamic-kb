"""Structured logging configuration for dynamic-kb."""

import logging
import os


def setup_logging() -> None:
    """Configure logging with format and level from environment."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,  # Override any existing configuration
    )


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a module.

    Args:
        name: Module name (e.g., "scraper", "ai_processor", "elevenlabs")

    Returns:
        Configured logger instance
    """
    return logging.getLogger(f"dynamic_kb.{name}")


# Initialize logging on module import
setup_logging()
