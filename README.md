# KB-Sync

**Knowledge Base Automation for ElevenLabs Voice Agents**

KB-Sync is a web scraping and knowledge base automation tool that crawls websites, extracts content into clean markdown using AI, and syncs knowledge bases with ElevenLabs' ConvAI system for voice agent training.

## Features

- **Web Scraping**: Crawl websites with configurable depth and page limits using [crawl4ai](https://github.com/unclecode/crawl4ai)
- **AI-Powered Content Processing**: Extract and clean content using Google Gemini with multimodal vision support
- **Change Detection**: Skip uploads when content hasn't changed (content hashing)
- **ElevenLabs Integration**: Automatic KB upload, RAG indexing, and agent configuration updates
- **Streamlit UI**: Web-based dashboard for managing sources, viewing history, and running syncs
- **Docker Ready**: Easy deployment with Docker and docker-compose

## Quick Start

### Prerequisites

- Python 3.11+
- Google Gemini API key ([get one here](https://aistudio.google.com/app/apikey))
- ElevenLabs API key ([get one here](https://elevenlabs.io/app/settings/api-keys))

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/kb-sync.git
cd kb-sync
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install Playwright browsers (for crawl4ai):
```bash
playwright install chromium
```

5. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your API keys
```

6. Configure sources in `config.yaml` (see Configuration section)

### Running the Application

**Web UI (Streamlit):**
```bash
streamlit run app/main.py
```
Then open http://localhost:8501 in your browser.

**Docker:**
```bash
docker-compose up -d
```
Access at http://localhost:8501

## Configuration

### config.yaml

```yaml
sources:
  - name: "My Website"
    url: "https://example.com/news"
    enabled: true
    schedule: "0 8 * * *"  # Informational (for external scheduler)
    scraping:
      max_depth: 1
      max_pages: 5
      url_pattern: "^https://example\\.com/news"
      capture_screenshots: true
    prompts:
      # Optional custom prompts (use {start_url} and {content} placeholders)
      link_extraction: null
      content_cleaning: null
    elevenlabs:
      agent_ids:
        - "agent_xxx"
      kb_prefix: "MY_WEBSITE"
      remove_old_versions: true

settings:
  ai_provider: "gemini"
  gemini_model: "gemini-2.5-flash"
  change_detection: true
  dry_run: false
  data_dir: "data"
  output_dir: "data/outputs"
```

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GEMINI_API_KEY` | Google Gemini API key | Yes |
| `ELEVENLABS_API_KEY` | ElevenLabs API key | Yes |
| `CONFIG_PATH` | Path to config.yaml | No (default: `config.yaml`) |

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
│   │   └── config.py        # Pydantic models
│   ├── ui/
│   │   ├── dashboard.py     # Main dashboard
│   │   ├── sources.py       # Source management
│   │   ├── history.py       # Execution history
│   │   └── settings.py      # Settings page
│   └── utils/
│       └── storage.py       # File/state management
├── data/
│   ├── history.json         # Execution history
│   ├── content_hashes.json  # Change detection hashes
│   └── outputs/             # Generated KB files
├── config.yaml              # Configuration
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Data Flow

```
1. Load source configuration from config.yaml
2. Crawl initial URL with crawl4ai (+ screenshot)
3. Extract sub-page links using Gemini AI
4. Crawl sub-pages in parallel (up to max_pages)
5. Clean/deduplicate content via Gemini (multimodal)
6. Check for changes (content hashing)
7. If changed: save locally as markdown
8. Upload to ElevenLabs KB API
9. Trigger RAG indexing (e5_mistral_7b_instruct)
10. Update ElevenLabs agents with new KB
```

## UI Pages

### Dashboard
- Overall system status
- Last run summary per source
- Quick actions (run individual sources or all)

### Sources
- List all configured sources
- Add/edit/delete sources
- Enable/disable sources
- View configuration details

### History
- Execution log with timestamps
- Status filtering (success/failed/no_changes)
- View generated content
- Error details for failed runs

### Settings
- API key configuration
- Global settings (model, change detection, dry run)
- Default prompts reference

## Legacy Scripts

The original scripts are still available for reference:

- `update_kb.py` - Original production automation script
- `main.py` - Pydantic AI proof-of-concept

These can be used as standalone scripts or for reference when understanding the core logic.

## Development

### Running Tests

```bash
# TODO: Add tests
pytest
```

### Code Structure

- **Core modules** (`app/core/`): Business logic, can be used independently
- **Models** (`app/models/`): Pydantic models for configuration validation
- **UI** (`app/ui/`): Streamlit page components
- **Utils** (`app/utils/`): Storage and helper functions

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
