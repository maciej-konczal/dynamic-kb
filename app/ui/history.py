"""Execution history and version management page for dynamic-kb Streamlit UI."""

import streamlit as st

from app.models.config import AppConfig
from app.utils.storage import Storage
from app.utils.database import ExecutionRecord, ContentVersion


def render_history(config: AppConfig, storage: Storage):
    """Render the execution history page."""
    st.title("History & Versions")

    tab1, tab2 = st.tabs(["Execution History", "Content Versions"])

    with tab1:
        render_execution_history(config, storage)

    with tab2:
        render_content_versions(config, storage)


def render_execution_history(config: AppConfig, storage: Storage):
    """Render the execution history tab."""
    st.markdown("View past execution runs and their results")

    # Filters
    col1, col2, col3 = st.columns(3)

    with col1:
        source_options = ["All Sources"] + [s.name for s in config.sources]
        selected_source = st.selectbox("Filter by Source", source_options, key="hist_source")

    with col2:
        status_options = ["All", "success", "failed", "no_changes", "draft_created", "saved_locally", "rejected"]
        selected_status = st.selectbox("Filter by Status", status_options, key="hist_status")

    with col3:
        limit = st.number_input("Records to show", min_value=10, max_value=500, value=50, key="hist_limit")

    st.divider()

    # Get history
    source_filter = None if selected_source == "All Sources" else selected_source
    records = storage.get_history(source_name=source_filter, limit=limit)

    # Apply status filter
    if selected_status != "All":
        records = [r for r in records if r.status == selected_status]

    if not records:
        st.info("No execution records found matching the filters.")
        return

    # Summary stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total", len(records))
    with col2:
        success_count = len([r for r in records if r.status == "success"])
        st.metric("Successful", success_count)
    with col3:
        failed_count = len([r for r in records if r.status == "failed"])
        st.metric("Failed", failed_count)
    with col4:
        draft_count = len([r for r in records if r.status == "draft_created"])
        st.metric("Drafts Created", draft_count)

    st.divider()

    # Records table
    for record in records:
        render_execution_record(record, storage)


def render_execution_record(record: ExecutionRecord, storage: Storage):
    """Render a single execution record."""
    status_colors = {
        "success": "green",
        "failed": "red",
        "no_changes": "orange",
        "draft_created": "blue",
        "saved_locally": "blue",
        "rejected": "gray",
    }
    status_icons = {
        "success": "",
        "failed": "",
        "no_changes": "",
        "draft_created": "",
        "saved_locally": "",
        "rejected": "",
    }

    color = status_colors.get(record.status, "gray")
    icon = status_icons.get(record.status, "")

    with st.container():
        col1, col2, col3 = st.columns([3, 2, 2])

        with col1:
            st.markdown(f"**{record.source_name}**")
            st.caption(record.timestamp[:19])

        with col2:
            st.markdown(f":{color}[{icon} {record.status}]")
            if record.diff_summary:
                st.caption(record.diff_summary)

        with col3:
            if record.version_id:
                if st.button("View Content", key=f"view_exec_{record.id}"):
                    st.session_state["view_version_id"] = record.version_id
            if record.doc_id:
                st.caption(f"Doc: `{record.doc_id[:12]}...`")

        # Show error if failed
        if record.status == "failed" and record.error:
            st.error(f"Error: {record.error}")

    st.divider()


def render_content_versions(config: AppConfig, storage: Storage):
    """Render the content versions tab."""
    st.markdown("View and compare stored content versions")

    # Source selector
    source_options = [s.name for s in config.sources]
    if not source_options:
        st.info("No sources configured.")
        return

    selected_source = st.selectbox("Select Source", source_options, key="ver_source")

    # Get versions for selected source
    versions = storage.get_versions(selected_source, limit=20)

    if not versions:
        st.info(f"No versions stored for {selected_source}")
        return

    st.divider()

    # Version list
    col1, col2 = st.columns([1, 2])

    with col1:
        st.markdown("### Versions")
        for v in versions:
            pushed_label = " (pushed)" if v.doc_id else ""
            version_label = f"v{v.version_number}{pushed_label}"

            if st.button(
                version_label,
                key=f"ver_btn_{v.id}",
                type="primary" if st.session_state.get("selected_version_id") == v.id else "secondary",
            ):
                st.session_state["selected_version_id"] = v.id

            st.caption(f"{v.created_at[:19]}")
            st.caption(f"`{v.content_hash[:8]}...`")
            st.markdown("---")

    with col2:
        st.markdown("### Content")

        # Show selected version or first one
        selected_id = st.session_state.get("selected_version_id") or (versions[0].id if versions else None)

        if selected_id:
            version = storage.get_version_by_id(selected_id)
            if version:
                st.markdown(f"**Version {version.version_number}**")
                st.caption(f"Created: {version.created_at[:19]}")
                st.caption(f"Hash: `{version.content_hash}`")

                if version.doc_id:
                    st.success(f"Pushed to ElevenLabs: `{version.doc_id}`")
                    st.caption(f"Pushed at: {version.pushed_at[:19] if version.pushed_at else 'N/A'}")
                else:
                    st.info("Not pushed to ElevenLabs")

                st.divider()

                # Content preview
                st.markdown("**Content:**")
                st.markdown(version.content)

    st.divider()

    # Version comparison
    st.markdown("### Compare Versions")

    if len(versions) < 2:
        st.info("Need at least 2 versions to compare")
        return

    col1, col2 = st.columns(2)

    with col1:
        version_options = {f"v{v.version_number} ({v.created_at[:10]})": v.id for v in versions}
        selected_v1 = st.selectbox("Version A", list(version_options.keys()), key="compare_v1")

    with col2:
        selected_v2 = st.selectbox(
            "Version B",
            list(version_options.keys()),
            index=min(1, len(version_options) - 1),
            key="compare_v2",
        )

    if st.button("Compare"):
        v1 = storage.get_version_by_id(version_options[selected_v1])
        v2 = storage.get_version_by_id(version_options[selected_v2])

        if v1 and v2:
            col1, col2 = st.columns(2)

            with col1:
                st.markdown(f"**{selected_v1}**")
                st.caption(f"Hash: `{v1.content_hash[:12]}...`")
                st.text_area(
                    "Content A",
                    v1.content,
                    height=400,
                    key="compare_content_a",
                    disabled=True,
                )

            with col2:
                st.markdown(f"**{selected_v2}**")
                st.caption(f"Hash: `{v2.content_hash[:12]}...`")
                st.text_area(
                    "Content B",
                    v2.content,
                    height=400,
                    key="compare_content_b",
                    disabled=True,
                )

            # Simple diff stats
            if v1.content_hash == v2.content_hash:
                st.success("Versions are identical")
            else:
                v1_lines = set(v1.content.split("\n"))
                v2_lines = set(v2.content.split("\n"))
                added = len(v2_lines - v1_lines)
                removed = len(v1_lines - v2_lines)
                st.info(f"Differences: +{added} lines, -{removed} lines")


# Handle view version modal from execution history
if "view_version_id" in st.session_state and st.session_state["view_version_id"]:
    # This will be handled by the main app
    pass
