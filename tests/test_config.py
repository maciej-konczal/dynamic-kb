"""Tests for app.models.config module."""

import tempfile
from pathlib import Path

import pytest
import yaml

from app.models.config import (
    AppConfig,
    SourceConfig,
    ScrapingConfig,
    PromptsConfig,
    ElevenLabsConfig,
    SettingsConfig,
    load_config,
    save_config,
)


class TestScrapingConfig:
    """Test ScrapingConfig model."""

    def test_default_values(self):
        """Test default values are set correctly."""
        config = ScrapingConfig()

        assert config.max_depth == 1
        assert config.max_pages == 5
        assert config.url_pattern is None
        assert config.capture_screenshots is True

    def test_custom_values(self):
        """Test custom values are accepted."""
        config = ScrapingConfig(
            max_depth=3,
            max_pages=10,
            url_pattern="^https://example\\.com",
            capture_screenshots=False,
        )

        assert config.max_depth == 3
        assert config.max_pages == 10
        assert config.url_pattern == "^https://example\\.com"
        assert config.capture_screenshots is False


class TestElevenLabsConfig:
    """Test ElevenLabsConfig model."""

    def test_minimal_config(self):
        """Test minimal required config (kb_prefix is required)."""
        config = ElevenLabsConfig(kb_prefix="TEST")

        assert config.agent_ids == []
        assert config.kb_prefix == "TEST"
        assert config.remove_old_versions is True

    def test_with_agent_ids(self):
        """Test with agent IDs."""
        config = ElevenLabsConfig(
            agent_ids=["agent_1", "agent_2"],
            kb_prefix="MY_KB",
        )

        assert len(config.agent_ids) == 2
        assert config.kb_prefix == "MY_KB"


class TestSourceConfig:
    """Test SourceConfig model."""

    def test_minimal_config(self):
        """Test minimal source configuration (elevenlabs required)."""
        config = SourceConfig(
            name="Test Source",
            url="https://example.com",
            elevenlabs=ElevenLabsConfig(kb_prefix="TEST"),
        )

        assert config.name == "Test Source"
        assert "example.com" in str(config.url)
        assert config.enabled is True

    def test_full_config(self, sample_source_config):
        """Test full source configuration."""
        config = SourceConfig(**sample_source_config)

        assert config.name == "Test Source"
        assert config.enabled is True
        assert config.scraping.max_depth == 1
        assert config.elevenlabs.kb_prefix == "TEST_KB"

    def test_url_validation(self):
        """Test URL validation."""
        config = SourceConfig(
            name="Test",
            url="https://example.com/path",
            elevenlabs=ElevenLabsConfig(kb_prefix="TEST"),
        )

        # Pydantic HttpUrl normalizes the URL
        assert "example.com" in str(config.url)


class TestSettingsConfig:
    """Test SettingsConfig model."""

    def test_default_values(self):
        """Test default settings values."""
        config = SettingsConfig()

        assert config.ai_provider == "gemini"
        assert config.gemini_model == "gemini-2.5-flash"
        assert config.change_detection is True
        assert config.dry_run is False
        assert config.data_dir == "data"
        assert config.output_dir == "data/outputs"


class TestAppConfig:
    """Test AppConfig model."""

    def test_empty_config(self):
        """Test config with no sources."""
        config = AppConfig(sources=[], settings=SettingsConfig())

        assert len(config.sources) == 0

    def test_with_sources(self, sample_source_config):
        """Test config with sources."""
        config = AppConfig(
            sources=[SourceConfig(**sample_source_config)],
            settings=SettingsConfig(),
        )

        assert len(config.sources) == 1
        assert config.sources[0].name == "Test Source"


class TestConfigIO:
    """Test config loading and saving."""

    def test_load_config(self, sample_source_config):
        """Test loading config from YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(
                {
                    "sources": [sample_source_config],
                    "settings": {"gemini_model": "gemini-2.5-pro"},
                },
                f,
            )
            f.flush()

            config = load_config(f.name)

            assert len(config.sources) == 1
            assert config.sources[0].name == "Test Source"
            assert config.settings.gemini_model == "gemini-2.5-pro"

    def test_load_config_file_not_found(self):
        """Test loading nonexistent config file."""
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")

    def test_save_config(self, sample_source_config):
        """Test saving config to YAML file."""
        config = AppConfig(
            sources=[SourceConfig(**sample_source_config)],
            settings=SettingsConfig(),
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            save_config(config, f.name)

            # Reload and verify
            loaded = load_config(f.name)
            assert loaded.sources[0].name == config.sources[0].name

    def test_config_roundtrip(self, sample_source_config):
        """Test that config survives save/load cycle."""
        original = AppConfig(
            sources=[SourceConfig(**sample_source_config)],
            settings=SettingsConfig(
                gemini_model="gemini-2.5-pro",
                dry_run=True,
            ),
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            save_config(original, f.name)
            loaded = load_config(f.name)

            assert loaded.sources[0].name == original.sources[0].name
            assert loaded.settings.gemini_model == original.settings.gemini_model
            assert loaded.settings.dry_run == original.settings.dry_run
