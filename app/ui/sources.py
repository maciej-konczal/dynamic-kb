"""Sources management page for dynamic-kb Streamlit UI."""

import streamlit as st
import yaml

from app.models.config import AppConfig, SourceConfig, ScrapingConfig, PromptsConfig, ElevenLabsConfig, save_config
from app.core.scheduler import validate_cron_expression, get_next_run_time, get_cron_description


def render_sources(config: AppConfig, config_path: str = "config.yaml"):
    """Render the sources management page."""
    st.title("Source Management")
    st.markdown("Configure data sources for knowledge base synchronization")

    # Add new source section
    with st.expander("Add New Source", expanded=False):
        render_source_form(config, config_path)

    st.divider()

    # List existing sources
    st.subheader("Configured Sources")

    if not config.sources:
        st.info("No sources configured. Add a source above to get started.")
        return

    for i, source in enumerate(config.sources):
        render_source_card(config, config_path, source, i)


def render_source_form(config: AppConfig, config_path: str, source: SourceConfig = None, index: int = None):
    """Render form for adding/editing a source."""
    is_edit = source is not None
    prefix = f"edit_{index}_" if is_edit else "new_"

    with st.form(f"{prefix}source_form"):
        col1, col2 = st.columns(2)

        with col1:
            name = st.text_input(
                "Source Name",
                value=source.name if is_edit else "",
                key=f"{prefix}name",
                help="Human-readable name for this source",
            )
            url = st.text_input(
                "URL",
                value=str(source.url) if is_edit else "",
                key=f"{prefix}url",
                help="URL to scrape",
            )
            enabled = st.checkbox(
                "Enabled",
                value=source.enabled if is_edit else True,
                key=f"{prefix}enabled",
            )

        with col2:
            kb_prefix = st.text_input(
                "KB Prefix",
                value=source.elevenlabs.kb_prefix if is_edit else "",
                key=f"{prefix}kb_prefix",
                help="Prefix for knowledge base document names",
            )
            agent_ids = st.text_area(
                "Agent IDs (one per line)",
                value="\n".join(source.elevenlabs.agent_ids) if is_edit else "",
                key=f"{prefix}agent_ids",
                help="ElevenLabs agent IDs to update",
            )
            schedule = st.text_input(
                "Schedule (cron)",
                value=source.schedule if is_edit and source.schedule else "",
                key=f"{prefix}schedule",
                help="Cron expression for scheduling (e.g., '0 8 * * *' for daily at 8am)",
            )

            # Show schedule validation and preview
            if schedule:
                valid, error = validate_cron_expression(schedule)
                if valid:
                    next_run = get_next_run_time(schedule)
                    description = get_cron_description(schedule)
                    if next_run:
                        st.caption(f"{description} - Next: {next_run.strftime('%Y-%m-%d %H:%M')}")
                else:
                    st.error(error)

            schedule_enabled = st.checkbox(
                "Schedule Enabled",
                value=source.schedule_enabled if is_edit else True,
                key=f"{prefix}schedule_enabled",
                help="Enable/disable scheduled runs without removing the schedule",
            )

        st.markdown("**Scraping Settings**")
        col1, col2, col3 = st.columns(3)

        with col1:
            max_depth = st.number_input(
                "Max Depth",
                min_value=0,
                max_value=5,
                value=source.scraping.max_depth if is_edit else 1,
                key=f"{prefix}max_depth",
            )
        with col2:
            max_pages = st.number_input(
                "Max Pages",
                min_value=1,
                max_value=20,
                value=source.scraping.max_pages if is_edit else 5,
                key=f"{prefix}max_pages",
            )
        with col3:
            capture_screenshots = st.checkbox(
                "Capture Screenshots",
                value=source.scraping.capture_screenshots if is_edit else True,
                key=f"{prefix}screenshots",
            )

        url_pattern = st.text_input(
            "URL Pattern (regex)",
            value=source.scraping.url_pattern if is_edit and source.scraping.url_pattern else "",
            key=f"{prefix}url_pattern",
            help="Regex pattern to filter URLs (leave empty for no filtering)",
        )

        st.markdown("**Custom Prompts (optional)**")
        link_prompt = st.text_area(
            "Link Extraction Prompt",
            value=source.prompts.link_extraction if is_edit and source.prompts.link_extraction else "",
            key=f"{prefix}link_prompt",
            help="Custom prompt for extracting links (use {start_url} and {content} placeholders)",
            height=100,
        )
        content_prompt = st.text_area(
            "Content Cleaning Prompt",
            value=source.prompts.content_cleaning if is_edit and source.prompts.content_cleaning else "",
            key=f"{prefix}content_prompt",
            help="Custom prompt for cleaning content (use {start_url} and {content} placeholders)",
            height=100,
        )

        submitted = st.form_submit_button("Save Source" if is_edit else "Add Source")

        if submitted:
            if not name or not url or not kb_prefix:
                st.error("Name, URL, and KB Prefix are required")
                return

            # Validate cron expression if provided
            if schedule:
                valid, error = validate_cron_expression(schedule)
                if not valid:
                    st.error(f"Invalid schedule: {error}")
                    return

            # Build source config
            new_source = SourceConfig(
                name=name,
                url=url,
                enabled=enabled,
                schedule=schedule if schedule else None,
                schedule_enabled=schedule_enabled,
                scraping=ScrapingConfig(
                    max_depth=max_depth,
                    max_pages=max_pages,
                    url_pattern=url_pattern if url_pattern else None,
                    capture_screenshots=capture_screenshots,
                ),
                prompts=PromptsConfig(
                    link_extraction=link_prompt if link_prompt else None,
                    content_cleaning=content_prompt if content_prompt else None,
                ),
                elevenlabs=ElevenLabsConfig(
                    agent_ids=[aid.strip() for aid in agent_ids.split("\n") if aid.strip()],
                    kb_prefix=kb_prefix,
                ),
            )

            if is_edit:
                config.sources[index] = new_source
            else:
                config.sources.append(new_source)

            save_config(config, config_path)
            st.success(f"Source {'updated' if is_edit else 'added'} successfully!")
            st.rerun()


def render_source_card(config: AppConfig, config_path: str, source: SourceConfig, index: int):
    """Render a card for an existing source."""
    with st.container():
        col1, col2 = st.columns([4, 1])

        with col1:
            status_icon = "" if source.enabled else ""
            st.markdown(f"### {status_icon} {source.name}")
            st.markdown(f"**URL:** {source.url}")
            st.markdown(f"**KB Prefix:** `{source.elevenlabs.kb_prefix}`")
            st.markdown(f"**Agents:** {len(source.elevenlabs.agent_ids)} configured")
            if source.schedule:
                description = get_cron_description(source.schedule)
                status = "" if source.schedule_enabled else " (paused)"
                st.markdown(f"**Schedule:** `{source.schedule}` - {description}{status}")
                if source.schedule_enabled:
                    next_run = get_next_run_time(source.schedule)
                    if next_run:
                        st.caption(f"Next run: {next_run.strftime('%Y-%m-%d %H:%M')}")

        with col2:
            if st.button("Edit", key=f"edit_btn_{index}"):
                st.session_state[f"editing_{index}"] = True

            if st.button("Delete", key=f"delete_btn_{index}", type="secondary"):
                st.session_state[f"confirm_delete_{index}"] = True

        # Edit form
        if st.session_state.get(f"editing_{index}"):
            with st.expander("Edit Source", expanded=True):
                render_source_form(config, config_path, source, index)
                if st.button("Cancel", key=f"cancel_edit_{index}"):
                    st.session_state[f"editing_{index}"] = False
                    st.rerun()

        # Delete confirmation
        if st.session_state.get(f"confirm_delete_{index}"):
            st.warning(f"Are you sure you want to delete '{source.name}'?")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Yes, Delete", key=f"confirm_yes_{index}", type="primary"):
                    config.sources.pop(index)
                    save_config(config, config_path)
                    st.success("Source deleted")
                    st.rerun()
            with col2:
                if st.button("Cancel", key=f"confirm_no_{index}"):
                    st.session_state[f"confirm_delete_{index}"] = False
                    st.rerun()

    st.divider()
