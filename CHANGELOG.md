# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2025-01-31

### Added

- **Observability** - Enterprise-grade monitoring and tracing:
  - Langfuse integration for LLM call tracing (inputs, outputs, token usage, latency)
  - Prometheus-compatible metrics for scraping, AI, ElevenLabs, and KB operations
  - Metrics persistence to SQLite/Supabase with historical charts
  - New Health page with service status, metrics dashboard, and maintenance tools
- **Reliability improvements**:
  - Custom exception hierarchy (`DynamicKBError`, `ScraperError`, `AIProcessorError`, `ElevenLabsError`, `ConfigurationError`)
  - Structured logging with configurable `LOG_LEVEL` environment variable
  - Configurable timeouts for scraper (30s default) and AI processor (60s default)
  - Exponential backoff retry logic (1s, 2s, 4s) for transient failures
  - API key validation on startup with clear error messages
- New Supabase table `metrics_events` for metrics persistence
- Comprehensive test suite (156 tests) covering all new modules

### Changed

- Scraper now accepts `timeout` and `source_name` parameters
- AIProcessor now accepts `timeout` and `max_retries` parameters
- ElevenLabsClient now accepts `source_name` for metrics tracking
- Health page now shows historical metrics with time series charts

## [1.0.0] - 2025-01-28

### Added

- Web scraping with [crawl4ai](https://github.com/unclecode/crawl4ai) - configurable depth, page limits, URL pattern filtering
- AI content processing with Google Gemini 2.5 Flash - multimodal vision support for screenshot extraction
- ElevenLabs ConvAI integration - automatic KB upload, RAG indexing, and agent updates
- Streamlit web dashboard with four pages:
  - Dashboard - status overview and quick run actions
  - Sources - CRUD for source configurations
  - History - execution logs with filtering
  - Settings - API keys and global settings
- Draft review workflow - preview and approve content before pushing to production
- Change detection - only push updates when content actually changes
- Version history - SQLite-backed storage with full version history
- Database options - SQLite (local) or Supabase (cloud)
- Docker support with docker-compose
- One-click deploy support for Railway and Render
- CI/CD workflow with GitHub Actions
