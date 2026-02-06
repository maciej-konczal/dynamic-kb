# Dynamic-KB

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.30+-FF4B4B.svg)](https://streamlit.io)
[![ElevenLabs](https://img.shields.io/badge/ElevenLabs-ConvAI-black.svg)](https://elevenlabs.io)

**Knowledge Base Automation for ElevenLabs Voice Agents**

Dynamic-KB automatically crawls websites, extracts and cleans content using AI, and syncs knowledge bases with ElevenLabs voice agents. Perfect for keeping your AI assistants up-to-date with the latest information.

## Features

- **Web Scraping** - Crawl websites with configurable depth using [crawl4ai](https://github.com/unclecode/crawl4ai)
- **AI Content Processing** - Clean and deduplicate content with Google Gemini (multimodal vision support)
- **Built-in Scheduler** - Cron-based scheduling with SQLite persistence, survives restarts
- **Preview Before Push** - Review scraped content and compare with previous versions before syncing
- **Change Detection** - Only push updates when content actually changes
- **Version History** - SQLite/Supabase storage with full version history and rollback
- **ElevenLabs Integration** - Automatic KB upload, RAG indexing, and agent updates
- **Observability** - LLM tracing with Langfuse, metrics with Prometheus, health monitoring
- **Inventory Mode** - Extract structured data per page (e.g., car listings) and generate formatted reports
- **Enterprise Ready** - Structured logging, retries with exponential backoff, custom exceptions
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
cp config.example.yaml config.yaml
# Edit .env with your API keys and config.yaml with your sources
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

## Inventory Mode

For sources where each sub-page represents a distinct item (e.g., car listings, product pages, real estate), **inventory mode** extracts structured data per page and generates a formatted report instead of combining all pages into one document.

### How It Works

1. Crawl the source and discover sub-page links (same as generic mode)
2. For each sub-page, extract structured JSON fields using Gemini (e.g., title, price, mileage)
3. Generate a markdown report with a summary table and per-item detail sections
4. Save as draft for review, then push to ElevenLabs

### Example: Car Dealership

```yaml
sources:
  - name: "AutoMax Inventory"
    url: "https://automax-dealer.com/cars"
    mode: "inventory"
    scraping:
      max_depth: 1
      max_pages: 20
      url_pattern: "automax-dealer\\.com/cars/"
    inventory:
      report_title: "AutoMax Current Inventory"
      fields:
        - title
        - price
        - year
        - mileage
        - fuel
        - engine
        - transmission
        - color
        - description
      summary_fields:
        - title
        - year
        - mileage
        - price
    elevenlabs:
      agent_ids:
        - "agent_automax"
      kb_prefix: "AUTOMAX_INV"
```

### Scaling Up

Add more dealers (or any item-based source) by adding more entries to `config.yaml`. Each source scrapes independently and produces its own report. Use scheduling to keep inventories fresh automatically.

## Configuration

### config.yaml

```yaml
sources:
  - name: "My Website News"
    url: "https://example.com/news"
    enabled: true
    schedule: "0 8 * * *"       # Cron expression (daily at 8am)
    schedule_enabled: true      # Can pause without removing schedule
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

### Scheduling

Dynamic-KB includes a built-in scheduler that runs inside the Streamlit process. Jobs persist in SQLite and survive app restarts.

#### Adding a Schedule

Add a `schedule` field to any source in `config.yaml`:

```yaml
sources:
  - name: "Daily Docs Sync"
    url: "https://docs.example.com"
    schedule: "0 8 * * *"        # Daily at 8:00 AM
    schedule_enabled: true       # Toggle without removing schedule
    # ... rest of config
```

#### Common Cron Expressions

| Expression | Description |
|------------|-------------|
| `0 8 * * *` | Daily at 8:00 AM |
| `0 */2 * * *` | Every 2 hours |
| `*/30 * * * *` | Every 30 minutes |
| `0 9 * * 1` | Every Monday at 9:00 AM |
| `0 0 1 * *` | First day of month at midnight |
| `0 8 * * 1-5` | Weekdays at 8:00 AM |

#### Managing Schedules

Use the **Scheduler** page in the web UI to:
- View all scheduled jobs with next run times
- Pause/resume individual jobs or all jobs
- Sync scheduler with config changes
- Start/stop the scheduler

#### How Scheduled Jobs Work

1. When a scheduled job runs, it scrapes the source automatically
2. If content changed, it creates a **draft** (not auto-pushed to ElevenLabs)
3. You review and approve drafts on the **Dashboard** page
4. Missed jobs during downtime are recovered when the app restarts (up to 1 hour late)

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GEMINI_API_KEY` | Google Gemini API key | Yes |
| `ELEVENLABS_API_KEY` | ElevenLabs API key | Yes |
| `CONFIG_PATH` | Path to config.yaml | No |
| `SUPABASE_URL` | Supabase project URL | No |
| `SUPABASE_KEY` | Supabase Publishable key | No |
| `LANGFUSE_PUBLIC_KEY` | Langfuse public key for LLM tracing | No |
| `LANGFUSE_SECRET_KEY` | Langfuse secret key | No |
| `LANGFUSE_HOST` | Langfuse host URL (default: cloud.langfuse.com) | No |
| `LOG_LEVEL` | Logging level: DEBUG, INFO, WARNING, ERROR (default: INFO) | No |

### Database Options

By default, Dynamic-KB uses **SQLite** for local storage. For cloud deployments or shared access, you can use **Supabase**.

#### Local (SQLite - Default)
No configuration needed. Data is stored in `data/kb_sync.db`.

#### Cloud (Supabase)
1. Create a project at [supabase.com](https://supabase.com)
2. Run the following SQL in the Supabase SQL Editor:

```sql
-- content_versions table
CREATE TABLE content_versions (
    id SERIAL PRIMARY KEY,
    source_name TEXT NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    doc_id TEXT,
    pushed_at TIMESTAMPTZ,
    version_number INTEGER DEFAULT 1,
    UNIQUE(source_name, content_hash)
);

-- content_drafts table
CREATE TABLE content_drafts (
    id SERIAL PRIMARY KEY,
    source_name TEXT NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT DEFAULT 'pending',
    diff_summary TEXT,
    previous_version_id INTEGER REFERENCES content_versions(id)
);

-- execution_history table
CREATE TABLE execution_history (
    id SERIAL PRIMARY KEY,
    source_name TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL,
    content_hash TEXT,
    doc_id TEXT,
    error TEXT,
    diff_summary TEXT,
    version_id INTEGER REFERENCES content_versions(id)
);

-- metrics_events table (for observability)
CREATE TABLE metrics_events (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metric_name TEXT NOT NULL,
    metric_value DOUBLE PRECISION NOT NULL,
    labels JSONB DEFAULT '{}'::jsonb
);

-- Indexes for performance
CREATE INDEX idx_versions_source ON content_versions(source_name);
CREATE INDEX idx_drafts_source ON content_drafts(source_name);
CREATE INDEX idx_drafts_status ON content_drafts(status);
CREATE INDEX idx_history_source ON execution_history(source_name);
CREATE INDEX idx_metrics_name ON metrics_events(metric_name);
CREATE INDEX idx_metrics_timestamp ON metrics_events(timestamp);
```

3. Copy your credentials from Project Settings → API and add to `.env`:
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_publishable_key
```

The app automatically uses Supabase when these variables are set.

### Observability (Optional)

Dynamic-KB includes enterprise-grade observability features:

#### Langfuse (LLM Tracing)
Track all AI calls with inputs, outputs, token usage, and latency.

1. Create a free account at [cloud.langfuse.com](https://cloud.langfuse.com)
2. Get your API keys from Settings → API Keys
3. Add to `.env`:
```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

#### Metrics (Prometheus-compatible)
Application metrics are automatically persisted to your database (SQLite or Supabase) and displayed on the Health page. Tracked metrics include:
- AI requests, retries, and token usage
- Scraping operations and duration
- ElevenLabs API calls
- Knowledge base document operations
- Health check status

View metrics on the **Health** page in the web UI.

## Architecture

```
dynamic-kb/
├── app/
│   ├── main.py              # Streamlit entry point
│   ├── core/
│   │   ├── scraper.py       # Web crawling (crawl4ai)
│   │   ├── ai_processor.py  # Gemini content processing
│   │   ├── elevenlabs.py    # ElevenLabs API client
│   │   ├── scheduler.py     # APScheduler with SQLite persistence
│   │   ├── scheduled_tasks.py # Task wrappers for scheduler
│   │   ├── differ.py        # Change detection
│   │   ├── report_generator.py # Inventory report formatting
│   │   ├── quality_assessor.py # LLM-based content quality scoring
│   │   ├── exceptions.py    # Custom exception types
│   │   ├── logging.py       # Structured logging
│   │   ├── metrics.py       # Prometheus metrics
│   │   ├── metrics_storage.py # Metrics persistence
│   │   └── observability.py # Langfuse LLM tracing
│   ├── models/
│   │   └── config.py        # Pydantic config models
│   ├── ui/
│   │   ├── dashboard.py     # Main dashboard
│   │   ├── sources.py       # Source management
│   │   ├── scheduler.py     # Scheduler management
│   │   ├── history.py       # Version history
│   │   ├── settings.py      # Settings page
│   │   └── health.py        # Health & metrics page
│   └── utils/
│       ├── database.py      # SQLite backend
│       ├── supabase_db.py   # Supabase backend
│       └── storage.py       # Storage abstraction
├── data/
│   └── kb_sync.db           # SQLite database (local)
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
- **Car Dealership Inventory** - Extract structured listings and generate inventory reports for voice agents
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
