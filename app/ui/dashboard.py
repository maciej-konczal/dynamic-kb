"""Dashboard page for dynamic-kb Streamlit UI."""

import asyncio
from datetime import datetime

import streamlit as st

from app.models.config import AppConfig, SourceConfig
from app.utils.storage import Storage
from app.utils.database import ContentDraft
from app.core.scraper import Scraper
from app.core.ai_processor import AIProcessor
from app.core.elevenlabs import ElevenLabsClient, KBDocument
from app.core.differ import ContentDiffer
from app.core.exceptions import ScraperError, AIProcessorError, ElevenLabsError


async def scrape_source(
    source: SourceConfig,
    settings: AppConfig,
    gemini_key: str,
) -> tuple[str, str, str]:
    """Scrape and process content from a source. Returns (content, hash, diff_summary)."""
    # Initialize components
    scraper = Scraper(
        max_depth=source.scraping.max_depth,
        max_pages=source.scraping.max_pages,
        url_pattern=source.scraping.url_pattern,
        capture_screenshots=source.scraping.capture_screenshots,
    )
    ai_processor = AIProcessor(
        api_key=gemini_key,
        model=settings.settings.gemini_model,
        link_extraction_prompt=source.prompts.link_extraction,
        content_cleaning_prompt=source.prompts.content_cleaning,
    )

    # Step 1: Crawl initial page
    st.write(f"Crawling {source.url}...")
    initial_result = await scraper.crawl_url(str(source.url))
    if not initial_result.success:
        raise ScraperError(f"Failed to crawl: {initial_result.error}")

    # Step 2: Extract links
    st.write("Extracting sub-page links...")
    ai_links = await ai_processor.extract_links(
        initial_result.markdown,
        str(source.url),
    )

    # Merge with include_urls (priority URLs come first)
    include_urls = source.scraping.include_urls or []
    all_links = list(dict.fromkeys(include_urls + ai_links))  # Dedupe, preserve order
    st.write(f"Found {len(ai_links)} AI-extracted + {len(include_urls)} priority URLs = {len(all_links)} total")

    # Step 3: Crawl sub-pages
    st.write("Crawling sub-pages...")
    results = await scraper.crawl_with_subpages(str(source.url), all_links)
    combined_content, screenshots = scraper.combine_results(results)

    # Step 4: Clean content
    st.write("Cleaning and processing content...")
    clean_content = await ai_processor.clean_content(
        combined_content,
        str(source.url),
        screenshots,
    )

    # Compute hash
    content_hash = ContentDiffer.compute_hash(clean_content)

    # Generate diff summary
    differ = ContentDiffer()
    diff_summary = f"New content generated (hash: {content_hash[:8]}...)"

    return clean_content, content_hash, diff_summary


async def push_to_elevenlabs(
    source: SourceConfig,
    content: str,
    storage: Storage,
    version_id: int,
    elevenlabs_key: str,
) -> str:
    """Push content to ElevenLabs and update agents. Returns doc_id."""
    el_client = ElevenLabsClient(api_key=elevenlabs_key)

    kb_name = f"{source.elevenlabs.kb_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    st.write(f"Uploading to ElevenLabs as: {kb_name}")

    doc_id = await el_client.create_kb_text(kb_name, content)
    st.write(f"Created KB document: {doc_id}")

    # Trigger RAG indexing if enabled
    if source.elevenlabs.trigger_rag_index:
        st.write("Triggering RAG indexing...")
        await el_client.trigger_rag_index(doc_id)

    # Update agents
    new_doc = KBDocument(id=doc_id, name=kb_name)
    for agent_id in source.elevenlabs.agent_ids:
        removed, success = await el_client.update_agent_kb(
            agent_id,
            new_doc,
            source.elevenlabs.kb_prefix,
            source.elevenlabs.remove_old_versions,
        )
        if success:
            st.write(f"Updated agent: {agent_id}")
        else:
            st.warning(f"Failed to update agent: {agent_id}")

    # Update version with doc_id
    storage.update_version_doc_id(version_id, doc_id)

    return doc_id


def render_pending_drafts(config: AppConfig, storage: Storage):
    """Render pending drafts section."""
    drafts = storage.get_pending_drafts()

    if not drafts:
        return

    st.subheader(f"Pending Drafts ({len(drafts)})")
    st.markdown("Review and approve content before pushing to ElevenLabs")

    elevenlabs_key = st.session_state.get("elevenlabs_api_key", "")

    for draft in drafts:
        render_draft_card(draft, config, storage, elevenlabs_key)


def render_draft_card(draft: ContentDraft, config: AppConfig, storage: Storage, elevenlabs_key: str):
    """Render a single draft card with preview and actions."""
    # Find source config
    source = next((s for s in config.sources if s.name == draft.source_name), None)

    with st.container():
        col1, col2 = st.columns([3, 1])

        with col1:
            st.markdown(f"### {draft.source_name}")
            st.caption(f"Created: {draft.created_at[:19]} | Hash: `{draft.content_hash[:12]}...`")
            if draft.diff_summary:
                st.info(draft.diff_summary)

        with col2:
            if source and source.elevenlabs.agent_ids:
                st.markdown("**Will update agents:**")
                for agent_id in source.elevenlabs.agent_ids:
                    st.caption(f"`{agent_id}`")
            else:
                st.markdown("**No agents configured**")

        # Preview expander
        with st.expander("Preview Content", expanded=False):
            st.markdown(draft.content)

        # Compare with previous version
        if draft.previous_version_id:
            previous = storage.get_version_by_id(draft.previous_version_id)
            if previous:
                with st.expander("Compare with Previous Version", expanded=False):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**Previous (pushed)**")
                        st.caption(f"Hash: `{previous.content_hash[:12]}...`")
                        st.text_area(
                            "Previous",
                            previous.content[:5000],
                            height=300,
                            key=f"prev_{draft.id}",
                            disabled=True,
                        )
                    with col2:
                        st.markdown("**New (draft)**")
                        st.caption(f"Hash: `{draft.content_hash[:12]}...`")
                        st.text_area(
                            "New",
                            draft.content[:5000],
                            height=300,
                            key=f"new_{draft.id}",
                            disabled=True,
                        )

        # Action buttons
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("Approve & Push", key=f"approve_{draft.id}", type="primary", disabled=not elevenlabs_key):
                if not elevenlabs_key:
                    st.error("ElevenLabs API key required")
                elif not source:
                    st.error("Source configuration not found")
                else:
                    with st.spinner("Approving and pushing to ElevenLabs..."):
                        # Approve draft (creates version)
                        version = storage.approve_draft(draft.id)
                        if version:
                            # Push to ElevenLabs
                            try:
                                doc_id = asyncio.run(push_to_elevenlabs(
                                    source,
                                    draft.content,
                                    storage,
                                    version.id,
                                    elevenlabs_key,
                                ))
                                storage.add_execution(
                                    source_name=draft.source_name,
                                    status="success",
                                    content_hash=draft.content_hash,
                                    doc_id=doc_id,
                                    version_id=version.id,
                                )
                                st.success(f"Pushed to ElevenLabs! Doc ID: {doc_id}")
                            except ElevenLabsError as e:
                                storage.add_execution(
                                    source_name=draft.source_name,
                                    status="failed",
                                    content_hash=draft.content_hash,
                                    error=str(e),
                                    version_id=version.id,
                                )
                                st.error(f"ElevenLabs error: {e}")
                            except Exception as e:
                                storage.add_execution(
                                    source_name=draft.source_name,
                                    status="failed",
                                    content_hash=draft.content_hash,
                                    error=str(e),
                                    version_id=version.id,
                                )
                                st.error(f"Unexpected error: {e}")
                        st.rerun()

        with col2:
            if st.button("Save Only", key=f"save_{draft.id}"):
                # Approve without pushing
                version = storage.approve_draft(draft.id)
                if version:
                    storage.add_execution(
                        source_name=draft.source_name,
                        status="saved_locally",
                        content_hash=draft.content_hash,
                        version_id=version.id,
                    )
                    st.success("Saved as version (not pushed)")
                st.rerun()

        with col3:
            if st.button("Reject", key=f"reject_{draft.id}", type="secondary"):
                storage.reject_draft(draft.id)
                storage.add_execution(
                    source_name=draft.source_name,
                    status="rejected",
                    content_hash=draft.content_hash,
                )
                st.info("Draft rejected")
                st.rerun()

    st.divider()


def render_dashboard(config: AppConfig, storage: Storage):
    """Render the dashboard page."""
    st.title("dynamic-kb Dashboard")
    st.markdown("Knowledge Base Automation for ElevenLabs Voice Agents")

    # API Keys from session state
    gemini_key = st.session_state.get("gemini_api_key", "")
    elevenlabs_key = st.session_state.get("elevenlabs_api_key", "")

    if not gemini_key:
        st.warning("Gemini API key not configured. Go to Settings to add it.")

    # Quick stats
    col1, col2, col3, col4 = st.columns(4)
    enabled_sources = [s for s in config.sources if s.enabled]
    pending_drafts = storage.get_pending_drafts()

    with col1:
        st.metric("Total Sources", len(config.sources))
    with col2:
        st.metric("Enabled Sources", len(enabled_sources))
    with col3:
        st.metric("Pending Drafts", len(pending_drafts))
    with col4:
        history = storage.get_history()
        total = len(history)
        success_count = len([h for h in history if h.status == "success"])
        if total > 0:
            percentage = int((success_count / total) * 100)
            st.metric("Success Rate", f"{percentage}%", help=f"{success_count}/{total} successful")
        else:
            st.metric("Success Rate", "N/A")

    st.divider()

    # Pending Drafts Section (if any)
    render_pending_drafts(config, storage)

    # Source Status Overview
    st.subheader("Sources")

    for source in config.sources:
        last_run = storage.get_last_execution(source.name)
        latest_version = storage.get_latest_version(source.name)
        pending = storage.get_pending_drafts(source.name)

        with st.container():
            col1, col2, col3, col4 = st.columns([3, 2, 2, 2])

            with col1:
                status_icon = "" if source.enabled else ""
                st.markdown(f"**{status_icon} {source.name}**")
                st.caption(str(source.url))
                if latest_version and latest_version.pushed_at:
                    st.caption(f"Last pushed: {latest_version.pushed_at[:19]}")

            with col2:
                if pending:
                    st.markdown(":orange[Draft pending]")
                elif last_run:
                    status_color = {
                        "success": "green",
                        "failed": "red",
                        "no_changes": "orange",
                        "saved_locally": "blue",
                        "rejected": "gray",
                    }.get(last_run.status, "gray")
                    st.markdown(f":{status_color}[{last_run.status}]")
                else:
                    st.markdown(":gray[Never run]")

            with col3:
                if latest_version and latest_version.doc_id:
                    st.caption(f"Doc: `{latest_version.doc_id[:12]}...`")

            with col4:
                if source.enabled and gemini_key and not pending:
                    if st.button("Scrape", key=f"scrape_{source.name}"):
                        with st.spinner(f"Scraping {source.name}..."):
                            try:
                                content, content_hash, diff_summary = asyncio.run(
                                    scrape_source(source, config, gemini_key)
                                )

                                # Check if content changed
                                latest = storage.get_latest_version(source.name)
                                if latest and latest.content_hash == content_hash:
                                    storage.add_execution(
                                        source_name=source.name,
                                        status="no_changes",
                                        content_hash=content_hash,
                                    )
                                    st.info("No changes detected")
                                else:
                                    # Create draft for review
                                    draft = storage.create_draft(
                                        source.name,
                                        content,
                                        content_hash,
                                        diff_summary,
                                    )
                                    storage.add_execution(
                                        source_name=source.name,
                                        status="draft_created",
                                        content_hash=content_hash,
                                        diff_summary=diff_summary,
                                    )
                                    st.success("Draft created! Review above.")

                            except ScraperError as e:
                                storage.add_execution(
                                    source_name=source.name,
                                    status="failed",
                                    error=str(e),
                                )
                                st.error(f"Scraping error: {e}")
                            except AIProcessorError as e:
                                storage.add_execution(
                                    source_name=source.name,
                                    status="failed",
                                    error=str(e),
                                )
                                st.error(f"AI processing error: {e}")
                            except Exception as e:
                                storage.add_execution(
                                    source_name=source.name,
                                    status="failed",
                                    error=str(e),
                                )
                                st.error(f"Unexpected error: {e}")

                            st.rerun()

        st.divider()

    # Bulk Actions
    st.subheader("Bulk Actions")
    col1, col2 = st.columns(2)

    with col1:
        if enabled_sources and gemini_key:
            if st.button("Scrape All Enabled Sources"):
                progress_bar = st.progress(0)
                status_text = st.empty()

                for i, source in enumerate(enabled_sources):
                    pending = storage.get_pending_drafts(source.name)
                    if pending:
                        status_text.text(f"Skipping {source.name} (has pending draft)")
                        continue

                    status_text.text(f"Scraping {source.name}...")
                    try:
                        content, content_hash, diff_summary = asyncio.run(
                            scrape_source(source, config, gemini_key)
                        )

                        latest = storage.get_latest_version(source.name)
                        if latest and latest.content_hash == content_hash:
                            storage.add_execution(
                                source_name=source.name,
                                status="no_changes",
                                content_hash=content_hash,
                            )
                        else:
                            storage.create_draft(
                                source.name,
                                content,
                                content_hash,
                                diff_summary,
                            )
                            storage.add_execution(
                                source_name=source.name,
                                status="draft_created",
                                content_hash=content_hash,
                            )

                    except (ScraperError, AIProcessorError) as e:
                        storage.add_execution(
                            source_name=source.name,
                            status="failed",
                            error=str(e),
                        )
                    except Exception as e:
                        storage.add_execution(
                            source_name=source.name,
                            status="failed",
                            error=f"Unexpected: {e}",
                        )

                    progress_bar.progress((i + 1) / len(enabled_sources))

                status_text.text("Done! Review drafts above.")
                st.rerun()

    with col2:
        drafts = storage.get_pending_drafts()
        if drafts and elevenlabs_key:
            if st.button("Approve & Push All Drafts", type="primary"):
                for draft in drafts:
                    source = next((s for s in config.sources if s.name == draft.source_name), None)
                    if source:
                        version = storage.approve_draft(draft.id)
                        if version:
                            try:
                                doc_id = asyncio.run(push_to_elevenlabs(
                                    source,
                                    draft.content,
                                    storage,
                                    version.id,
                                    elevenlabs_key,
                                ))
                                storage.add_execution(
                                    source_name=draft.source_name,
                                    status="success",
                                    content_hash=draft.content_hash,
                                    doc_id=doc_id,
                                    version_id=version.id,
                                )
                            except ElevenLabsError as e:
                                storage.add_execution(
                                    source_name=draft.source_name,
                                    status="failed",
                                    error=str(e),
                                )
                            except Exception as e:
                                storage.add_execution(
                                    source_name=draft.source_name,
                                    status="failed",
                                    error=f"Unexpected: {e}",
                                )
                st.success("All drafts processed!")
                st.rerun()
