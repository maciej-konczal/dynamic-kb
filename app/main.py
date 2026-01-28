"""dynamic-kb: Streamlit UI Entry Point.

Run with: streamlit run app/main.py
"""

import os
import sys
from pathlib import Path

import streamlit as st

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.config import load_config, AppConfig, SettingsConfig
from app.utils.storage import Storage
from app.ui.dashboard import render_dashboard
from app.ui.sources import render_sources
from app.ui.history import render_history
from app.ui.settings import render_settings


# Page configuration
st.set_page_config(
    page_title="dynamic-kb",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)


def load_app_config() -> tuple[AppConfig, str]:
    """Load application configuration."""
    config_path = os.getenv("CONFIG_PATH", "config.yaml")

    try:
        config = load_config(config_path)
    except FileNotFoundError:
        # Create default config if not exists
        st.warning(f"Config file not found at {config_path}. Using default configuration.")
        config = AppConfig(
            sources=[],
            settings=SettingsConfig(),
        )

    return config, config_path


def main():
    """Main application entry point."""
    # Load configuration
    config, config_path = load_app_config()

    # Initialize storage
    storage = Storage(data_dir=config.settings.data_dir)

    # Load API keys from environment if not in session state
    if "gemini_api_key" not in st.session_state:
        st.session_state["gemini_api_key"] = os.getenv("GEMINI_API_KEY", "")
    if "elevenlabs_api_key" not in st.session_state:
        st.session_state["elevenlabs_api_key"] = os.getenv("ELEVENLABS_API_KEY", "")

    # Sidebar navigation
    st.sidebar.title("dynamic-kb")
    st.sidebar.markdown("Knowledge Base Automation")

    page = st.sidebar.radio(
        "Navigation",
        options=["Dashboard", "Sources", "History", "Settings"],
        index=0,
    )

    st.sidebar.divider()

    # Quick status in sidebar
    st.sidebar.markdown("**Quick Status**")
    enabled_count = len([s for s in config.sources if s.enabled])
    st.sidebar.markdown(f"Sources: {enabled_count}/{len(config.sources)} enabled")

    if st.session_state.get("gemini_api_key"):
        st.sidebar.markdown(" Gemini: Connected")
    else:
        st.sidebar.markdown(" Gemini: Not configured")

    if st.session_state.get("elevenlabs_api_key"):
        st.sidebar.markdown(" ElevenLabs: Connected")
    else:
        st.sidebar.markdown(" ElevenLabs: Not configured")

    if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"):
        st.sidebar.markdown(" Supabase: Connected")
    else:
        st.sidebar.markdown(" Supabase: Using SQLite")

    st.sidebar.divider()
    st.sidebar.markdown(
        "Made with [crawl4ai](https://github.com/unclecode/crawl4ai) & "
        "[ElevenLabs](https://elevenlabs.io)"
    )

    # Render selected page
    if page == "Dashboard":
        render_dashboard(config, storage)
    elif page == "Sources":
        render_sources(config, config_path)
    elif page == "History":
        render_history(config, storage)
    elif page == "Settings":
        render_settings(config, config_path)


if __name__ == "__main__":
    main()
