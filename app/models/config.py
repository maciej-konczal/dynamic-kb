"""Pydantic models for configuration validation."""

from typing import Literal, Optional
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, HttpUrl


DEFAULT_INVENTORY_FIELDS = [
    "title", "price", "year", "mileage", "fuel", "engine", "power",
    "transmission", "drive", "body_type", "color", "doors", "seats",
    "condition", "description", "equipment",
]

DEFAULT_SUMMARY_FIELDS = ["title", "year", "mileage", "fuel", "price"]


class InventoryConfig(BaseModel):
    """Configuration for inventory-mode processing."""

    report_title: str = Field(default="Inventory Report", description="Title for the generated report")
    fields: list[str] = Field(default_factory=lambda: list(DEFAULT_INVENTORY_FIELDS), description="Fields to extract per item")
    summary_fields: list[str] = Field(default_factory=lambda: list(DEFAULT_SUMMARY_FIELDS), description="Fields for overview table")


class ScrapingConfig(BaseModel):
    """Configuration for web scraping behavior."""

    max_depth: int = Field(default=1, ge=0, le=5, description="Maximum depth of sub-page crawling")
    max_pages: int = Field(default=5, ge=1, le=20, description="Maximum number of pages to crawl")
    url_pattern: Optional[str] = Field(default=None, description="Regex pattern to filter URLs")
    capture_screenshots: bool = Field(default=True, description="Whether to capture page screenshots")
    include_urls: list[str] = Field(default_factory=list, description="URLs to always include (crawled first)")


class PromptsConfig(BaseModel):
    """Custom prompts for AI processing."""

    link_extraction: Optional[str] = Field(default=None, description="Custom prompt for link extraction")
    content_cleaning: Optional[str] = Field(default=None, description="Custom prompt for content cleaning")
    extraction_prompt: Optional[str] = Field(default=None, description="Custom prompt for structured extraction in inventory mode (use {fields} and {content} placeholders)")


class ElevenLabsConfig(BaseModel):
    """ElevenLabs-specific configuration."""

    agent_ids: list[str] = Field(default_factory=list, description="List of agent IDs to update")
    kb_prefix: str = Field(description="Prefix for KB document names")
    remove_old_versions: bool = Field(default=True, description="Whether to remove old KB versions from agents")
    trigger_rag_index: bool = Field(default=True, description="Whether to trigger RAG indexing after upload")


class SourceConfig(BaseModel):
    """Configuration for a single data source."""

    name: str = Field(description="Human-readable name for the source")
    url: HttpUrl = Field(description="URL to scrape")
    enabled: bool = Field(default=True, description="Whether this source is active")
    mode: Literal["generic", "inventory"] = Field(default="generic", description="Processing mode: generic (default) or inventory")
    schedule: Optional[str] = Field(default=None, description="Cron expression for scheduling")
    schedule_enabled: bool = Field(default=True, description="Whether scheduled runs are enabled (allows pausing without removing schedule)")
    scraping: ScrapingConfig = Field(default_factory=ScrapingConfig)
    prompts: PromptsConfig = Field(default_factory=PromptsConfig)
    inventory: Optional[InventoryConfig] = Field(default=None, description="Inventory mode configuration (only used when mode='inventory')")
    elevenlabs: ElevenLabsConfig


class SettingsConfig(BaseModel):
    """Global application settings."""

    ai_provider: str = Field(default="gemini", description="AI provider to use")
    gemini_model: str = Field(default="gemini-2.5-flash", description="Gemini model name")
    change_detection: bool = Field(default=True, description="Skip upload if content unchanged")
    dry_run: bool = Field(default=False, description="Run without making external API calls")
    data_dir: str = Field(default="data", description="Directory for data storage")
    output_dir: str = Field(default="data/outputs", description="Directory for output files")
    quality_scoring_enabled: bool = Field(default=False, description="Enable LLM-based quality scoring for scraped content")
    quality_auto_approve_threshold: int = Field(default=80, ge=0, le=100, description="Auto-approve drafts with quality score >= this value (0-100)")
    quality_auto_reject_threshold: int = Field(default=30, ge=0, le=100, description="Auto-reject drafts with quality score <= this value (0-100)")


class AppConfig(BaseModel):
    """Root application configuration."""

    sources: list[SourceConfig] = Field(default_factory=list, description="List of data sources")
    settings: SettingsConfig = Field(default_factory=SettingsConfig)


def load_config(config_path: str = "config.yaml") -> AppConfig:
    """Load and validate configuration from YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(path, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f)

    return AppConfig(**raw_config)


def save_config(config: AppConfig, config_path: str = "config.yaml") -> None:
    """Save configuration to YAML file."""
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            config.model_dump(mode="json"),
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
