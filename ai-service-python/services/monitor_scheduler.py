"""Background scheduler for research monitors.

Runs a lightweight polling loop that checks active monitors with
frequency='daily' once per hour. Monitors that have already been checked
within the last 24 hours are skipped.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

_logger = logging.getLogger(__name__)

_CHECK_INTERVAL_SECONDS = 3600  # 1 hour
_DAILY_WINDOW_HOURS = 24

_scheduler_thread: threading.Thread | None = None
_stop_event = threading.Event()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _run_loop() -> None:
    """Background loop: every hour, check all active daily monitors."""
    _logger.info("Monitor scheduler started (interval=%ds).", _CHECK_INTERVAL_SECONDS)

    while not _stop_event.is_set():
        try:
            _tick()
        except Exception:
            _logger.exception("Monitor scheduler tick failed.")

        _stop_event.wait(_CHECK_INTERVAL_SECONDS)

    _logger.info("Monitor scheduler stopped.")


def _tick() -> None:
    from services import research_monitor as rm

    try:
        monitors = rm.list_monitors()
    except Exception:
        _logger.exception("Failed to list monitors.")
        return

    active_daily = [
        m for m in monitors
        if m.get("active") and str(m.get("frequency") or "").strip() == "daily"
    ]

    if not active_daily:
        return

    now = _utc_now()
    threshold = now - timedelta(hours=_DAILY_WINDOW_HOURS)

    for monitor in active_daily:
        monitor_id = str(monitor.get("monitor_id") or monitor.get("monitorId") or "")
        last_checked_str = str(monitor.get("last_checked") or monitor.get("lastChecked") or "")

        # Skip if checked within the window
        if last_checked_str:
            try:
                last_checked = datetime.fromisoformat(last_checked_str.replace("Z", "+00:00"))
                if last_checked > threshold:
                    continue
            except (ValueError, TypeError):
                pass

        try:
            result = rm.check_new_publications(monitor_id)
            new_count = result.get("newCount", 0)
            if new_count > 0:
                _logger.info(
                    "Monitor %s found %d new publications.", monitor_id, new_count,
                )
        except Exception:
            _logger.exception("Monitor %s check failed.", monitor_id)


def start_scheduler() -> None:
    """Start the background monitor scheduler in a daemon thread."""
    global _scheduler_thread, _stop_event

    if _scheduler_thread is not None and _scheduler_thread.is_alive():
        return

    _stop_event.clear()
    _scheduler_thread = threading.Thread(
        target=_run_loop, name="pixiu-monitor-scheduler", daemon=True,
    )
    _scheduler_thread.start()


def stop_scheduler() -> None:
    """Signal the scheduler to stop and wait for the thread to exit."""
    global _scheduler_thread

    _stop_event.set()
    if _scheduler_thread is not None and _scheduler_thread.is_alive():
        _scheduler_thread.join(timeout=5)
    _scheduler_thread = None


def is_running() -> bool:
    return _scheduler_thread is not None and _scheduler_thread.is_alive()
