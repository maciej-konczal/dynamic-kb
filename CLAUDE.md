# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KB-Sync is a Python-based web scraping and knowledge base automation platform. It crawls websites, extracts content into clean markdown using AI, and syncs knowledge bases with ElevenLabs' ConvAI system for voice agent training. Features a Streamlit web UI for easy management.

## Commands

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium  # Required for crawl4ai

# Run Streamlit Web UI
streamlit run app/main.py

# Docker deployment
docker-compose up -d

# Legacy scripts (for reference)
python update_kb.py  # Original production automation
python main.py       # Pydantic AI prototype
```

## Architecture

```
kb-sync/
├── app/
│   ├── main.py              # Streamlit UI entry point
│   ├── core/
│   │   ├── scraper.py       # Web crawling (crawl4ai)
│   │   ├── ai_processor.py  # Gemini content processing
│   │   ├── elevenlabs.py    # ElevenLabs API client
│   │   └── differ.py        # Content change detection
│   ├── models/
│   │   └── config.py        # Pydantic models for config
│   ├── ui/
│   │   ├── dashboard.py     # Main dashboard page
│   │   ├── sources.py       # Source management page
│   │   ├── history.py       # Execution history page
│   │   └── settings.py      # Settings page
│   └── utils/
│       └── storage.py       # File/state management
├── data/                    # Runtime data (gitignored)
│   ├── history.json         # Execution history
│   ├── content_hashes.json  # Change detection
│   └── outputs/             # Generated KB files
├── config.yaml              # Source configuration
├── update_kb.py             # Legacy production script
├── main.py                  # Legacy Pydantic AI prototype
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

### Core Modules

- **app/core/scraper.py** - `Scraper` class wrapping crawl4ai for web crawling with configurable depth, page limits, and URL pattern filtering
- **app/core/ai_processor.py** - `AIProcessor` class for Gemini-based link extraction and multimodal content cleaning
- **app/core/elevenlabs.py** - `ElevenLabsClient` class for KB CRUD, RAG indexing, and agent management
- **app/core/differ.py** - `ContentDiffer` class for content hashing and change detection

### Configuration

`config.yaml` is the main configuration file with:
- `sources[]` - Array of source configurations (URL, scraping options, prompts, ElevenLabs settings)
- `settings` - Global settings (AI model, change detection, dry run mode)

See `app/models/config.py` for Pydantic models defining the config schema.

### Data Flow

```
1. Load source from config.yaml
2. Crawl URL with crawl4ai (Scraper)
3. Extract sub-page links via Gemini (AIProcessor)
4. Crawl sub-pages up to max_pages limit
5. Clean content via Gemini with multimodal vision
6. Check for changes (ContentDiffer)
7. Save to data/outputs/ as markdown
8. Upload to ElevenLabs KB API
9. Trigger RAG indexing
10. Update agent knowledge base references
```

### External Integrations

- **Google Gemini 2.5 Flash** - Content extraction, link discovery, multimodal cleaning
- **ElevenLabs ConvAI API** - KB management, RAG indexing, agent configuration
- **crawl4ai** - Web scraping with Playwright, markdown + screenshot extraction

### Environment Variables

Required in `.env`:
- `GEMINI_API_KEY` - Google Gemini API key
- `ELEVENLABS_API_KEY` - ElevenLabs API key

Optional:
- `CONFIG_PATH` - Path to config.yaml (default: `config.yaml`)

## UI Pages

- **Dashboard** (`/`) - Status overview, quick run actions
- **Sources** (`/sources`) - CRUD for source configurations
- **History** (`/history`) - Execution logs with filtering
- **Settings** (`/settings`) - API keys and global settings
