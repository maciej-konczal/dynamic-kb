"""dynamic-kb: Streamlit UI Entry Point.

Run with: streamlit run app/main.py
"""

import asyncio
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
from app.ui.health import render_health_page
from app.core.logging import get_logger

logger = get_logger("main")


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


def validate_gemini_api_key(api_key: str) -> tuple[bool, str]:
    """Validate Gemini API key by attempting to list models.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not api_key:
        return False, "API key not provided"

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        # List models to validate the API key
        list(client.models.list())
        logger.info("Gemini API key validated successfully")
        return True, ""
    except Exception as e:
        error_msg = str(e)
        logger.warning(f"Gemini API key validation failed: {error_msg}")
        return False, error_msg


async def validate_elevenlabs_api_key_async(api_key: str) -> tuple[bool, str]:
    """Validate ElevenLabs API key by listing agents.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not api_key:
        return False, "API key not provided"

    try:
        from app.core.elevenlabs import ElevenLabsClient
        client = ElevenLabsClient(api_key=api_key)
        await client.list_agents()
        logger.info("ElevenLabs API key validated successfully")
        return True, ""
    except Exception as e:
        error_msg = str(e)
        logger.warning(f"ElevenLabs API key validation failed: {error_msg}")
        return False, error_msg


def validate_elevenlabs_api_key(api_key: str) -> tuple[bool, str]:
    """Synchronous wrapper for ElevenLabs API key validation."""
    return asyncio.run(validate_elevenlabs_api_key_async(api_key))


def validate_api_keys() -> dict:
    """Validate API keys and return status.

    Returns:
        Dict with 'gemini' and 'elevenlabs' keys, each containing
        {'valid': bool, 'error': str}
    """
    # Use cached validation results if available
    if "api_validation_cache" in st.session_state:
        cache = st.session_state["api_validation_cache"]
        gemini_key = st.session_state.get("gemini_api_key", "")
        elevenlabs_key = st.session_state.get("elevenlabs_api_key", "")

        # Return cached results if keys haven't changed
        if (cache.get("gemini_key") == gemini_key and
            cache.get("elevenlabs_key") == elevenlabs_key):
            return cache.get("results", {})

    gemini_key = st.session_state.get("gemini_api_key", "")
    elevenlabs_key = st.session_state.get("elevenlabs_api_key", "")

    results = {
        "gemini": {"valid": False, "error": "Not configured"},
        "elevenlabs": {"valid": False, "error": "Not configured"},
    }

    if gemini_key:
        valid, error = validate_gemini_api_key(gemini_key)
        results["gemini"] = {"valid": valid, "error": error}

    if elevenlabs_key:
        valid, error = validate_elevenlabs_api_key(elevenlabs_key)
        results["elevenlabs"] = {"valid": valid, "error": error}

    # Cache the results
    st.session_state["api_validation_cache"] = {
        "gemini_key": gemini_key,
        "elevenlabs_key": elevenlabs_key,
        "results": results,
    }

    return results


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

    # Validate API keys
    api_status = validate_api_keys()

    # Sidebar navigation
    st.sidebar.title("dynamic-kb")
    st.sidebar.markdown("Knowledge Base Automation")

    page = st.sidebar.radio(
        "Navigation",
        options=["Dashboard", "Sources", "History", "Settings", "Health"],
        index=0,
    )

    st.sidebar.divider()

    # Quick status in sidebar
    st.sidebar.markdown("**Quick Status**")
    enabled_count = len([s for s in config.sources if s.enabled])
    st.sidebar.markdown(f"Sources: {enabled_count}/{len(config.sources)} enabled")

    # Gemini status with validation
    if st.session_state.get("gemini_api_key"):
        if api_status["gemini"]["valid"]:
            st.sidebar.markdown(" Gemini: Connected")
        else:
            st.sidebar.markdown(" Gemini: Invalid key")
            with st.sidebar.expander("Error details"):
                st.error(api_status["gemini"]["error"])
    else:
        st.sidebar.markdown(" Gemini: Not configured")

    # ElevenLabs status with validation
    if st.session_state.get("elevenlabs_api_key"):
        if api_status["elevenlabs"]["valid"]:
            st.sidebar.markdown(" ElevenLabs: Connected")
        else:
            st.sidebar.markdown(" ElevenLabs: Invalid key")
            with st.sidebar.expander("Error details"):
                st.error(api_status["elevenlabs"]["error"])
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
    elif page == "Health":
        render_health_page()


if __name__ == "__main__":
    main()
