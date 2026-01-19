"""Settings page for KB-Sync Streamlit UI."""

import os

import streamlit as st

from app.models.config import AppConfig, SettingsConfig, save_config


def render_settings(config: AppConfig, config_path: str = "config.yaml"):
    """Render the settings page."""
    st.title("Settings")
    st.markdown("Configure global application settings and API keys")

    # API Keys Section
    st.subheader("API Keys")
    st.markdown(
        "API keys are stored in session state and not persisted to disk. "
        "For production use, set them as environment variables."
    )

    col1, col2 = st.columns(2)

    with col1:
        # Load from environment or session state
        gemini_key = st.text_input(
            "Gemini API Key",
            value=st.session_state.get("gemini_api_key", os.getenv("GEMINI_API_KEY", "")),
            type="password",
            key="gemini_input",
            help="Google Gemini API key for AI processing",
        )
        if gemini_key:
            st.session_state["gemini_api_key"] = gemini_key
            st.success("Gemini API key configured")

    with col2:
        elevenlabs_key = st.text_input(
            "ElevenLabs API Key",
            value=st.session_state.get("elevenlabs_api_key", os.getenv("ELEVENLABS_API_KEY", "")),
            type="password",
            key="elevenlabs_input",
            help="ElevenLabs API key for KB synchronization",
        )
        if elevenlabs_key:
            st.session_state["elevenlabs_api_key"] = elevenlabs_key
            st.success("ElevenLabs API key configured")

    st.divider()

    # Global Settings Section
    st.subheader("Global Settings")

    with st.form("settings_form"):
        col1, col2 = st.columns(2)

        with col1:
            ai_provider = st.selectbox(
                "AI Provider",
                options=["gemini"],
                index=0,
                help="AI provider for content processing",
            )

            gemini_model = st.selectbox(
                "Gemini Model",
                options=["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
                index=["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"].index(config.settings.gemini_model)
                if config.settings.gemini_model in ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]
                else 0,
                help="Gemini model to use for processing",
            )

        with col2:
            change_detection = st.checkbox(
                "Enable Change Detection",
                value=config.settings.change_detection,
                help="Skip ElevenLabs upload if content hasn't changed",
            )

            dry_run = st.checkbox(
                "Dry Run Mode",
                value=config.settings.dry_run,
                help="Run without making external API calls (local save only)",
            )

        st.markdown("**Storage Paths**")
        col1, col2 = st.columns(2)

        with col1:
            data_dir = st.text_input(
                "Data Directory",
                value=config.settings.data_dir,
                help="Directory for storing state and history",
            )

        with col2:
            output_dir = st.text_input(
                "Output Directory",
                value=config.settings.output_dir,
                help="Directory for saving generated KB files",
            )

        submitted = st.form_submit_button("Save Settings")

        if submitted:
            config.settings = SettingsConfig(
                ai_provider=ai_provider,
                gemini_model=gemini_model,
                change_detection=change_detection,
                dry_run=dry_run,
                data_dir=data_dir,
                output_dir=output_dir,
            )
            save_config(config, config_path)
            st.success("Settings saved!")
            st.rerun()

    st.divider()

    # Default Prompts Section
    st.subheader("Default Prompts Reference")
    st.markdown(
        "These are the default prompts used when a source doesn't specify custom prompts. "
        "To customize, add prompts directly to each source configuration."
    )

    from app.core.ai_processor import AIProcessor

    with st.expander("Link Extraction Prompt"):
        st.code(AIProcessor.DEFAULT_LINK_EXTRACTION_PROMPT, language="text")

    with st.expander("Content Cleaning Prompt"):
        st.code(AIProcessor.DEFAULT_CONTENT_CLEANING_PROMPT, language="text")

    st.divider()

    # Environment Info
    st.subheader("Environment Information")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Environment Variables:**")
        st.markdown(f"- `GEMINI_API_KEY`: {'Set' if os.getenv('GEMINI_API_KEY') else 'Not set'}")
        st.markdown(f"- `ELEVENLABS_API_KEY`: {'Set' if os.getenv('ELEVENLABS_API_KEY') else 'Not set'}")
        st.markdown(f"- `CONFIG_PATH`: `{os.getenv('CONFIG_PATH', 'config.yaml')}`")

    with col2:
        st.markdown("**Current Configuration:**")
        st.markdown(f"- Config file: `{config_path}`")
        st.markdown(f"- Sources: {len(config.sources)}")
        st.markdown(f"- Data directory: `{config.settings.data_dir}`")
