# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Dynamic-KB is a Python-based web scraping and knowledge base automation platform. It crawls websites, extracts content into clean markdown using AI, and syncs knowledge bases with ElevenLabs' ConvAI system for voice agent training. Features a Streamlit web UI for easy management.

## Commands

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium  # Required for crawl4ai

# Run Streamlit Web UI
streamlit run app/main.py

# Run all tests
pytest

# Run a single test file
pytest tests/test_scheduler.py

# Run a specific test
pytest tests/test_scheduler.py::test_add_job

# Lint and format
ruff check .
ruff format .

# Docker deployment
docker-compose up -d
```

## Architecture

### Core Processing Pipeline

```
1. Load source from config.yaml
2. Crawl URL with crawl4ai (Scraper)
3. Extract sub-page links via Gemini (AIProcessor)
4. Crawl sub-pages up to max_pages limit
5. Clean content via Gemini with multimodal vision (generic mode) OR extract structured JSON per page (inventory mode)
6. Check for changes (ContentDiffer)
7. Save as draft for review
8. On approval: upload to ElevenLabs KB API
9. Trigger RAG indexing
10. Update agent knowledge base references
```

### Key Modules

**Core** (`app/core/`):
- `scraper.py` - `Scraper` class wrapping crawl4ai with configurable depth, page limits, timeout, URL filtering
- `ai_processor.py` - `AIProcessor` for Gemini-based link extraction and multimodal content cleaning with Langfuse tracing
- `elevenlabs.py` - `ElevenLabsClient` for KB CRUD, RAG indexing, and agent management
- `scheduler.py` - `SourceScheduler` singleton using APScheduler with SQLite persistence for cron-based job scheduling
- `scheduled_tasks.py` - Task wrappers that run during scheduled jobs (scrape → create draft)
- `differ.py` - `ContentDiffer` for content hashing and change detection
- `report_generator.py` - `generate_inventory_report()` for formatting structured extraction results into markdown reports
- `quality_assessor.py` - `QualityAssessor` for LLM-based content quality scoring with auto-approve/reject thresholds
- `exceptions.py` - Custom exception hierarchy (`DynamicKBError`, `ScraperError`, `AIProcessorError`, `ElevenLabsError`, `SchedulerError`, `ConfigurationError`)
- `observability.py` - Langfuse integration with `LangfuseTrace`, `LangfuseSpan`, `LangfuseGeneration` context managers
- `metrics.py` / `metrics_storage.py` - Prometheus-style metrics with DB persistence

**Storage** (`app/utils/`):
- `storage.py` - `Storage` facade that auto-selects SQLite or Supabase based on env vars
- `database.py` - SQLite backend implementing `DatabaseProtocol`
- `supabase_db.py` - Supabase backend implementing `DatabaseProtocol`

**UI** (`app/ui/`):
- `dashboard.py` - Main view with pending drafts, quick actions
- `sources.py` - CRUD for source configurations
- `scheduler.py` - View/manage scheduled jobs, pause/resume, sync with config
- `history.py` - Execution logs with filtering
- `settings.py` - API keys and global settings
- `health.py` - System health, Langfuse status, metrics charts

### Configuration

`config.yaml` defines sources and settings. See `app/models/config.py` for Pydantic models.

Key source fields:
- `mode` - Processing mode: `"generic"` (default) or `"inventory"` (structured extraction per page)
- `schedule` - Cron expression (e.g., `"0 8 * * *"` for daily at 8am)
- `schedule_enabled` - Toggle scheduling without removing the cron expression
- `scraping.url_pattern` - Regex to filter crawled URLs
- `scraping.include_urls` - Additional URLs to always include
- `prompts.extraction_prompt` - Custom prompt for inventory mode structured extraction (uses `{fields}` and `{content}` placeholders)
- `elevenlabs.agent_ids` - Agents to update with new KB content

### External Integrations

- **Google Gemini 2.5 Flash** - Content extraction, link discovery, multimodal cleaning
- **ElevenLabs ConvAI API** - KB management, RAG indexing, agent configuration
- **crawl4ai** - Web scraping with Playwright, markdown + screenshot extraction
- **APScheduler** - Background job scheduling with SQLite job store

### Environment Variables

Required:
- `GEMINI_API_KEY` - Google Gemini API key
- `ELEVENLABS_API_KEY` - ElevenLabs API key

Optional:
- `CONFIG_PATH` - Path to config.yaml (default: `config.yaml`)
- `SUPABASE_URL` / `SUPABASE_KEY` - Enables Supabase instead of SQLite
- `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` - LLM tracing
- `LOG_LEVEL` - DEBUG, INFO, WARNING, ERROR (default: `INFO`)
