"""Scheduler management page for dynamic-kb Streamlit UI."""

from datetime import datetime

import streamlit as st

from app.models.config import AppConfig
from app.core.scheduler import (
    get_scheduler,
    get_cron_description,
    get_next_run_time,
    JobInfo,
)
from app.core.metrics import set_active_scheduled_jobs


def render_scheduler_page(config: AppConfig):
    """Render the scheduler management page."""
    st.title("Scheduler")
    st.markdown("Manage automated scraping schedules")

    # Get scheduler instance
    scheduler = get_scheduler(config.settings.data_dir)

    # Scheduler status
    render_scheduler_status(scheduler, config)

    st.divider()

    # Scheduled jobs table
    render_jobs_table(scheduler, config)

    st.divider()

    # Quick reference
    render_cron_reference()


def render_scheduler_status(scheduler, config: AppConfig):
    """Render scheduler status and global controls."""
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        is_running = scheduler.is_running
        if is_running:
            st.success("Scheduler is running")
        else:
            st.warning("Scheduler is stopped")

    with col2:
        jobs = scheduler.get_all_jobs()
        active_count = len([j for j in jobs if not j.is_paused])
        paused_count = len([j for j in jobs if j.is_paused])

        st.metric("Active Jobs", active_count)
        set_active_scheduled_jobs(active_count)

    with col3:
        st.metric("Paused Jobs", paused_count)

    # Global controls
    st.subheader("Global Controls")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if not scheduler.is_running:
            if st.button("Start Scheduler", type="primary"):
                try:
                    scheduler.start()
                    st.success("Scheduler started")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to start scheduler: {e}")
        else:
            if st.button("Stop Scheduler"):
                scheduler.stop()
                st.info("Scheduler stopped")
                st.rerun()

    with col2:
        if st.button("Pause All Jobs"):
            scheduler.pause_all()
            st.info("All jobs paused")
            st.rerun()

    with col3:
        if st.button("Resume All Jobs"):
            scheduler.resume_all()
            st.success("All jobs resumed")
            st.rerun()

    with col4:
        if st.button("Sync with Config"):
            result = scheduler.sync_with_config(config.sources)
            st.success(
                f"Synced: {result['added']} added, {result['updated']} updated, "
                f"{result['removed']} removed"
            )
            st.rerun()


def render_jobs_table(scheduler, config: AppConfig):
    """Render the jobs table with controls."""
    st.subheader("Scheduled Jobs")

    jobs = scheduler.get_all_jobs()

    if not jobs:
        st.info(
            "No scheduled jobs. Add a schedule to your sources in the Sources page, "
            "then click 'Sync with Config' above."
        )

        # Show sources with schedules that could be synced
        sources_with_schedules = [s for s in config.sources if s.schedule]
        if sources_with_schedules:
            st.markdown("**Sources with schedules (ready to sync):**")
            for source in sources_with_schedules:
                st.markdown(f"- {source.name}: `{source.schedule}`")
        return

    # Create table header
    cols = st.columns([2, 2, 2, 2, 1, 1])
    with cols[0]:
        st.markdown("**Source**")
    with cols[1]:
        st.markdown("**Schedule**")
    with cols[2]:
        st.markdown("**Next Run**")
    with cols[3]:
        st.markdown("**Last Run**")
    with cols[4]:
        st.markdown("**Status**")
    with cols[5]:
        st.markdown("**Actions**")

    st.divider()

    # Render each job row
    for job in jobs:
        render_job_row(scheduler, job)


def render_job_row(scheduler, job: JobInfo):
    """Render a single job row."""
    cols = st.columns([2, 2, 2, 2, 1, 1])

    with cols[0]:
        st.markdown(f"**{job.source_name}**")

    with cols[1]:
        description = get_cron_description(job.cron_expression)
        st.markdown(f"`{job.cron_expression}`")
        st.caption(description)

    with cols[2]:
        if job.is_paused:
            st.markdown(":orange[Paused]")
        elif job.next_run_time:
            # Format next run time
            next_run_str = job.next_run_time.strftime("%Y-%m-%d %H:%M")
            # Calculate time until next run
            now = datetime.now()
            delta = job.next_run_time - now
            if delta.total_seconds() > 0:
                hours, remainder = divmod(int(delta.total_seconds()), 3600)
                minutes, _ = divmod(remainder, 60)
                if hours > 0:
                    time_until = f"in {hours}h {minutes}m"
                else:
                    time_until = f"in {minutes}m"
                st.markdown(next_run_str)
                st.caption(time_until)
            else:
                st.markdown(next_run_str)
        else:
            st.markdown("-")

    with cols[3]:
        if job.last_run_at:
            last_run_str = job.last_run_at[:16].replace("T", " ")
            status_color = {
                "success": "green",
                "draft_created": "green",
                "no_changes": "orange",
                "skipped": "gray",
                "failed": "red",
            }.get(job.last_run_status, "gray")
            st.markdown(f":{status_color}[{job.last_run_status}]")
            st.caption(last_run_str)
            if job.last_error:
                with st.expander("Error"):
                    st.error(job.last_error)
        else:
            st.markdown(":gray[Never run]")

    with cols[4]:
        if job.is_paused:
            st.markdown(":orange[Paused]")
        else:
            st.markdown(":green[Active]")

    with cols[5]:
        if job.is_paused:
            if st.button("Resume", key=f"resume_{job.source_name}"):
                scheduler.resume_job(job.source_name)
                st.rerun()
        else:
            if st.button("Pause", key=f"pause_{job.source_name}"):
                scheduler.pause_job(job.source_name)
                st.rerun()

    st.divider()


def render_cron_reference():
    """Render a quick cron expression reference."""
    with st.expander("Cron Expression Reference"):
        st.markdown("""
**Format:** `minute hour day month weekday`

| Field | Values |
|-------|--------|
| minute | 0-59 |
| hour | 0-23 |
| day | 1-31 |
| month | 1-12 |
| weekday | 0-6 (0=Sunday) |

**Special Characters:**
- `*` - any value
- `*/n` - every n units
- `n,m` - specific values
- `n-m` - range of values

**Common Examples:**
| Expression | Description |
|------------|-------------|
| `0 8 * * *` | Daily at 8:00 AM |
| `0 */2 * * *` | Every 2 hours |
| `*/30 * * * *` | Every 30 minutes |
| `0 9 * * 1` | Every Monday at 9:00 AM |
| `0 0 1 * *` | First day of month at midnight |
| `0 8 * * 1-5` | Weekdays at 8:00 AM |
        """)
