"""Health check page for dynamic-kb Streamlit UI."""

import asyncio
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import streamlit as st
import pandas as pd

from app.core.logging import get_logger
from app.core.metrics import get_metrics, record_health_check, HEALTH_CHECK_STATUS
from app.core.metrics_storage import get_metrics_storage, MetricsStorage
from app.core.observability import is_langfuse_enabled, get_langfuse

logger = get_logger("health")


async def check_gemini_health(api_key: str) -> tuple[bool, str, float]:
    """Check Gemini API health.

    Returns:
        Tuple of (healthy, message, duration_seconds)
    """
    if not api_key:
        return False, "API key not configured", 0.0

    start_time = time.time()
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        # List models to validate the API key
        models = list(client.models.list())
        duration = time.time() - start_time
        return True, f"Connected ({len(models)} models available)", duration
    except Exception as e:
        duration = time.time() - start_time
        return False, str(e), duration


async def check_elevenlabs_health(api_key: str) -> tuple[bool, str, float]:
    """Check ElevenLabs API health.

    Returns:
        Tuple of (healthy, message, duration_seconds)
    """
    if not api_key:
        return False, "API key not configured", 0.0

    start_time = time.time()
    try:
        from app.core.elevenlabs import ElevenLabsClient
        client = ElevenLabsClient(api_key=api_key)
        agents = await client.list_agents()
        duration = time.time() - start_time
        return True, f"Connected ({len(agents)} agents)", duration
    except Exception as e:
        duration = time.time() - start_time
        return False, str(e), duration


def check_langfuse_health() -> tuple[bool, str, float]:
    """Check Langfuse health.

    Returns:
        Tuple of (healthy, message, duration_seconds)
    """
    start_time = time.time()
    try:
        if not is_langfuse_enabled():
            return False, "Not configured (set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY)", 0.0

        client = get_langfuse()
        if client:
            duration = time.time() - start_time
            return True, "Connected", duration
        else:
            return False, "Client not initialized", 0.0
    except Exception as e:
        duration = time.time() - start_time
        return False, str(e), duration


def render_health_page():
    """Render the health check page."""
    st.title("System Health")
    st.markdown("Monitor the health of dynamic-kb components and dependencies")

    # Get API keys from session state
    gemini_key = st.session_state.get("gemini_api_key", "")
    elevenlabs_key = st.session_state.get("elevenlabs_api_key", "")

    # Health check button
    if st.button("Run Health Checks", type="primary"):
        with st.spinner("Running health checks..."):
            # Run health checks
            gemini_healthy, gemini_msg, gemini_duration = asyncio.run(
                check_gemini_health(gemini_key)
            )
            elevenlabs_healthy, elevenlabs_msg, elevenlabs_duration = asyncio.run(
                check_elevenlabs_health(elevenlabs_key)
            )
            langfuse_healthy, langfuse_msg, langfuse_duration = check_langfuse_health()

            # Record metrics
            record_health_check("gemini", gemini_healthy, gemini_duration)
            record_health_check("elevenlabs", elevenlabs_healthy, elevenlabs_duration)
            record_health_check("langfuse", langfuse_healthy, langfuse_duration)

            # Store in session state
            st.session_state["health_results"] = {
                "gemini": (gemini_healthy, gemini_msg, gemini_duration),
                "elevenlabs": (elevenlabs_healthy, elevenlabs_msg, elevenlabs_duration),
                "langfuse": (langfuse_healthy, langfuse_msg, langfuse_duration),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

    # Display results
    if "health_results" in st.session_state:
        results = st.session_state["health_results"]
        st.caption(f"Last checked: {results['timestamp']}")

        col1, col2, col3 = st.columns(3)

        # Gemini health
        with col1:
            healthy, msg, duration = results["gemini"]
            st.markdown("### Gemini API")
            if healthy:
                st.success(f" Healthy")
                st.caption(msg)
                st.caption(f"Latency: {duration*1000:.0f}ms")
            else:
                st.error(f" Unhealthy")
                st.caption(msg)

        # ElevenLabs health
        with col2:
            healthy, msg, duration = results["elevenlabs"]
            st.markdown("### ElevenLabs API")
            if healthy:
                st.success(f" Healthy")
                st.caption(msg)
                st.caption(f"Latency: {duration*1000:.0f}ms")
            else:
                st.error(f" Unhealthy")
                st.caption(msg)

        # Langfuse health
        with col3:
            healthy, msg, duration = results["langfuse"]
            st.markdown("### Langfuse")
            if healthy:
                st.success(f" Healthy")
                st.caption(msg)
                st.caption(f"Latency: {duration*1000:.0f}ms")
            else:
                st.warning(f" Not Connected")
                st.caption(msg)

    st.divider()

    # Prometheus Metrics section
    st.subheader("Prometheus Metrics")
    st.markdown("""
    Metrics are available for scraping by Prometheus. Use the button below to view
    the current metrics output.
    """)

    if st.button("View Metrics"):
        metrics_output = get_metrics().decode("utf-8")
        st.code(metrics_output, language="text")

    # Metrics endpoint info
    with st.expander("How to scrape metrics"):
        st.markdown("""
        **For Prometheus:**

        Since Streamlit doesn't easily expose a `/metrics` endpoint, you have two options:

        1. **Run a separate metrics server** (recommended for production):
        ```python
        from prometheus_client import start_http_server
        start_http_server(8000)  # Exposes metrics on port 8000
        ```

        2. **Use the pushgateway**:
        ```yaml
        # prometheus.yml
        scrape_configs:
          - job_name: 'pushgateway'
            static_configs:
              - targets: ['pushgateway:9091']
        ```

        **Available Metrics:**
        - `dynamic_kb_scrape_requests_total` - Total scrape requests
        - `dynamic_kb_scrape_duration_seconds` - Scrape duration histogram
        - `dynamic_kb_ai_requests_total` - AI processing requests
        - `dynamic_kb_ai_duration_seconds` - AI processing duration
        - `dynamic_kb_ai_tokens_total` - Token usage
        - `dynamic_kb_elevenlabs_requests_total` - ElevenLabs API requests
        - `dynamic_kb_health_check_status` - Component health (1=healthy, 0=unhealthy)
        """)

    st.divider()

    # Historical Metrics section
    st.subheader("Historical Metrics (Supabase)")

    storage = get_metrics_storage()

    if storage.is_enabled():
        # Show storage backend
        if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"):
            st.success(" Metrics are being stored in Supabase")
        else:
            st.info(" Metrics are being stored in SQLite")

        # Time range selector
        hours = st.selectbox(
            "Time Range",
            options=[1, 6, 12, 24, 48, 168],
            index=3,
            format_func=lambda x: f"{x} hour{'s' if x > 1 else ''}" if x < 24 else f"{x // 24} day{'s' if x // 24 > 1 else ''}"
        )

        # Summary statistics
        st.markdown("#### Key Metrics (Last {})".format(
            f"{hours} hours" if hours < 24 else f"{hours // 24} days"
        ))

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            summary = storage.get_summary("ai_requests_total", hours=hours)
            st.metric("AI Requests", int(summary.count))

        with col2:
            summary = storage.get_summary("scrape_requests_total", hours=hours)
            st.metric("Scrape Requests", int(summary.count))

        with col3:
            summary = storage.get_summary("elevenlabs_requests_total", hours=hours)
            st.metric("ElevenLabs Requests", int(summary.count))

        with col4:
            summary = storage.get_summary("ai_tokens_total", hours=hours)
            st.metric("Total Tokens", int(summary.total))

        # Time series charts
        st.markdown("#### Request Activity")

        # Get time series data
        ai_data = storage.get_time_series("ai_requests_total", hours=hours)
        scrape_data = storage.get_time_series("scrape_requests_total", hours=hours)

        if ai_data or scrape_data:
            # Combine data for chart
            chart_data = []

            for event in ai_data:
                chart_data.append({
                    "timestamp": event["timestamp"][:19],  # Trim to seconds
                    "type": "AI Requests",
                    "value": event["value"],
                })

            for event in scrape_data:
                chart_data.append({
                    "timestamp": event["timestamp"][:19],
                    "type": "Scrape Requests",
                    "value": event["value"],
                })

            if chart_data:
                df = pd.DataFrame(chart_data)
                df["timestamp"] = pd.to_datetime(df["timestamp"])

                # Aggregate by hour for cleaner visualization
                df["hour"] = df["timestamp"].dt.floor("h")
                hourly = df.groupby(["hour", "type"])["value"].sum().reset_index()

                if not hourly.empty:
                    pivot = hourly.pivot(index="hour", columns="type", values="value").fillna(0)
                    st.line_chart(pivot)
                else:
                    st.info("No activity data in selected time range")
            else:
                st.info("No activity data in selected time range")
        else:
            st.info("No metrics data available yet. Run some operations to generate metrics.")

        # Token usage chart
        st.markdown("#### Token Usage")
        token_data = storage.get_time_series("ai_tokens_total", hours=hours)

        if token_data:
            chart_data = []
            for event in token_data:
                token_type = event["labels"].get("token_type", "unknown")
                chart_data.append({
                    "timestamp": event["timestamp"][:19],
                    "type": f"{token_type.title()} Tokens",
                    "value": event["value"],
                })

            if chart_data:
                df = pd.DataFrame(chart_data)
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df["hour"] = df["timestamp"].dt.floor("h")
                hourly = df.groupby(["hour", "type"])["value"].sum().reset_index()

                if not hourly.empty:
                    pivot = hourly.pivot(index="hour", columns="type", values="value").fillna(0)
                    st.bar_chart(pivot)
        else:
            st.info("No token usage data yet")

        # Cleanup option
        with st.expander("Maintenance"):
            st.markdown("Old metrics can be cleaned up to save storage space.")
            days_to_keep = st.number_input("Keep metrics for (days)", min_value=1, max_value=365, value=30)
            if st.button("Clean Up Old Metrics"):
                deleted = storage.cleanup(days=days_to_keep)
                st.success(f"Deleted {deleted} old metric records")

    else:
        st.warning(" Metrics storage is not available")
        st.markdown("""
        To enable metrics persistence, configure either:

        **Supabase (recommended):**
        ```bash
        export SUPABASE_URL=https://your-project.supabase.co
        export SUPABASE_KEY=your_supabase_key
        ```

        **SQLite (automatic fallback):**
        Metrics will be stored in `data/kb_sync.db` if Supabase is not configured.

        **Note:** You need to create the `metrics_events` table in Supabase:
        ```sql
        CREATE TABLE metrics_events (
            id BIGSERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            metric_name TEXT NOT NULL,
            metric_value DOUBLE PRECISION NOT NULL,
            labels JSONB DEFAULT '{}'::jsonb
        );

        CREATE INDEX idx_metrics_name ON metrics_events(metric_name);
        CREATE INDEX idx_metrics_timestamp ON metrics_events(timestamp);
        ```
        """)

    st.divider()

    # Langfuse configuration section
    st.subheader("Langfuse Configuration")

    if is_langfuse_enabled():
        st.success(" Langfuse is enabled")
        st.markdown("""
        Langfuse is tracking LLM calls. View your traces at:
        [Langfuse Dashboard](https://cloud.langfuse.com)
        """)
    else:
        st.warning(" Langfuse is not configured")
        st.markdown("""
        To enable LLM observability with Langfuse, set the following environment variables:

        ```bash
        export LANGFUSE_PUBLIC_KEY=pk-lf-...
        export LANGFUSE_SECRET_KEY=sk-lf-...
        # Optional: for self-hosted Langfuse
        export LANGFUSE_HOST=https://your-langfuse-instance.com
        ```

        **Benefits of Langfuse:**
        - Track all LLM calls (prompts, completions)
        - Monitor token usage and costs
        - Debug failed generations
        - Analyze latency patterns
        """)

    st.divider()

    # Environment info
    st.subheader("Environment")
    import os

    env_vars = {
        "GEMINI_API_KEY": "***" if os.getenv("GEMINI_API_KEY") else "Not set",
        "ELEVENLABS_API_KEY": "***" if os.getenv("ELEVENLABS_API_KEY") else "Not set",
        "LANGFUSE_PUBLIC_KEY": "***" if os.getenv("LANGFUSE_PUBLIC_KEY") else "Not set",
        "LANGFUSE_SECRET_KEY": "***" if os.getenv("LANGFUSE_SECRET_KEY") else "Not set",
        "LANGFUSE_HOST": os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com (default)"),
        "LANGFUSE_ENABLED": os.getenv("LANGFUSE_ENABLED", "true (default)"),
        "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO (default)"),
    }

    for key, value in env_vars.items():
        st.text(f"{key}: {value}")
