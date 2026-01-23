# Dynamic-KB

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.30+-FF4B4B.svg)](https://streamlit.io)
[![ElevenLabs](https://img.shields.io/badge/ElevenLabs-ConvAI-black.svg)](https://elevenlabs.io)

**Knowledge Base Automation for ElevenLabs Voice Agents**

Dynamic-KB automatically crawls websites, extracts and cleans content using AI, and syncs knowledge bases with ElevenLabs voice agents. Perfect for keeping your AI assistants up-to-date with the latest information.

![Dynamic-KB Dashboard](docs/screenshot-dashboard.png)
*Dashboard showing sources, pending drafts, and execution status*

## Features

- **Web Scraping** - Crawl websites with configurable depth using [crawl4ai](https://github.com/unclecode/crawl4ai)
- **AI Content Processing** - Clean and deduplicate content with Google Gemini (multimodal vision support)
- **Preview Before Push** - Review scraped content and compare with previous versions before syncing
- **Change Detection** - Only push updates when content actually changes
- **Version History** - SQLite-backed storage with full version history and rollback
- **ElevenLabs Integration** - Automatic KB upload, RAG indexing, and agent updates
- **Web UI** - Streamlit dashboard for easy management
- **Cloud Ready** - One-click deploy to Railway, Render, or Docker

## One-Click Deploy

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/dynamic-kb?referralCode=dynamic-kb)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/maciej-konczal/dynamic-kb)

## Quick Start

### Prerequisites

- Python 3.11+
- [Google Gemini API key](https://aistudio.google.com/app/apikey)
- [ElevenLabs API key](https://elevenlabs.io/app/settings/api-keys)

### Installation

```bash
# Clone the repository
git clone https://github.com/maciej-konczal/dynamic-kb.git
cd dynamic-kb

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install browser for web scraping
playwright install chromium

# Configure environment
cp .env.example .env
# Edit .env with your API keys
```

### Run

```bash
# Start the web UI
streamlit run app/main.py --server.headless true

# Open http://localhost:8501
```

### Docker

```bash
# Build and run
docker-compose up -d

# Access at http://localhost:8501
```

## How It Works

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   1. Scrape     │────▶│   2. Process    │────▶│   3. Review     │
│   Website       │     │   with AI       │     │   Draft         │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   6. Update     │◀────│   5. RAG        │◀────│   4. Push to    │
│   Agents        │     │   Indexing      │     │   ElevenLabs    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

1. **Scrape** - Crawl website and sub-pages with screenshots
2. **Process** - Extract and clean content using Gemini AI
3. **Review** - Preview draft, compare with previous version
4. **Push** - Upload to ElevenLabs Knowledge Base
5. **Index** - Trigger RAG indexing for semantic search
6. **Update** - Link new KB to your voice agents

## Configuration

### config.yaml

```yaml
sources:
  - name: "My Website News"
    url: "https://example.com/news"
    enabled: true
    scraping:
      max_depth: 1
      max_pages: 5
      url_pattern: "^https://example\\.com/news"
    elevenlabs:
      agent_ids:
        - "agent_xxx"
      kb_prefix: "WEBSITE_NEWS"

settings:
  gemini_model: "gemini-2.5-flash"
  change_detection: true
```

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GEMINI_API_KEY` | Google Gemini API key | Yes |
| `ELEVENLABS_API_KEY` | ElevenLabs API key | Yes |
| `CONFIG_PATH` | Path to config.yaml | No |

## Screenshots

### Dashboard
![Dashboard](docs/screenshot-dashboard.png)

### Draft Review
![Draft Review](docs/screenshot-draft.png)

### Version History
![History](docs/screenshot-history.png)

## Architecture

```
dynamic-kb/
├── app/
│   ├── main.py              # Streamlit entry point
│   ├── core/
│   │   ├── scraper.py       # Web crawling (crawl4ai)
│   │   ├── ai_processor.py  # Gemini content processing
│   │   ├── elevenlabs.py    # ElevenLabs API client
│   │   └── differ.py        # Change detection
│   ├── models/
│   │   └── config.py        # Pydantic config models
│   ├── ui/
│   │   ├── dashboard.py     # Main dashboard
│   │   ├── sources.py       # Source management
│   │   ├── history.py       # Version history
│   │   └── settings.py      # Settings page
│   └── utils/
│       ├── database.py      # SQLite backend
│       └── storage.py       # Storage abstraction
├── data/
│   └── kb_sync.db           # SQLite database
├── config.yaml              # Source configuration
├── Dockerfile
├── docker-compose.yml
├── railway.json             # Railway deploy config
└── render.yaml              # Render deploy config
```

## Use Cases

- **Customer Support Bots** - Keep FAQ and documentation up-to-date
- **News Assistants** - Sync latest news articles to voice agents
- **Product Assistants** - Update product catalogs and specs
- **Internal Tools** - Sync company wikis and documentation

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- [crawl4ai](https://github.com/unclecode/crawl4ai) - Web scraping
- [ElevenLabs](https://elevenlabs.io) - Voice AI platform
- [Google Gemini](https://deepmind.google/technologies/gemini/) - AI content processing
- [Streamlit](https://streamlit.io) - Web UI framework

---

**Made for the ElevenLabs community**
