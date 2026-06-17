from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from cal_sync.config import AppConfig
from cal_sync.google_calendar import apply_sync_plan, build_google_service, list_google_events
from cal_sync.lark_caldav import list_lark_events
from cal_sync.logging_config import configure_logging
from cal_sync.sync import SyncPlan, build_sync_plan

LOGGER = logging.getLogger(__name__)
ProgressReporter = Callable[[str], None]


def sync_once(config: AppConfig, progress: ProgressReporter | None = None) -> SyncPlan:
    configure_logging(config.log_path)
    start, end = sync_window(config.sync.past_days, config.sync.future_days)
    LOGGER.info("Sync started: start=%s end=%s", start.isoformat(), end.isoformat())
    _report(progress, "Sync window: %s -> %s", start.isoformat(), end.isoformat())

    _report(progress, "Loading Lark CalDAV events...")
    lark_events = list_lark_events(config.caldav, start, end)
    LOGGER.info("Loaded Lark events: count=%s", len(lark_events))
    _report(progress, "Loaded %s Lark events.", len(lark_events))

    _report(progress, "Authorizing Google Calendar...")
    google_service = build_google_service(config.google)

    _report(progress, "Loading Google Calendar events...")
    google_events = list_google_events(google_service, config.google.calendar_id, start, end)
    LOGGER.info("Loaded Google events: count=%s", len(google_events))
    _report(progress, "Loaded %s Google events.", len(google_events))

    plan = build_sync_plan(lark_events, google_events)

    LOGGER.info(
        "Sync plan: create=%s update=%s delete=%s dry_run=%s",
        len(plan.to_create),
        len(plan.to_update),
        len(plan.to_delete),
        config.sync.dry_run,
    )
    _report(
        progress,
        "Plan: create=%s update=%s delete=%s dry_run=%s",
        len(plan.to_create),
        len(plan.to_update),
        len(plan.to_delete),
        config.sync.dry_run,
    )
    if not config.sync.dry_run:
        _report(progress, "Applying changes to Google Calendar...")
        apply_sync_plan(google_service, config.google.calendar_id, plan)
        LOGGER.info("Applied Google Calendar changes")
        _report(progress, "Applied changes to Google Calendar.")
    else:
        LOGGER.info("Dry run enabled")
        _report(progress, "Dry run enabled. Google Calendar was not modified.")
    LOGGER.info("Sync finished")
    return plan


def sync_window(past_days: int, future_days: int) -> tuple[datetime, datetime]:
    now = datetime.now(tz=ZoneInfo("Asia/Shanghai"))
    return now - timedelta(days=past_days), now + timedelta(days=future_days)


def _report(progress: ProgressReporter | None, message: str, *args: object) -> None:
    if progress is None:
        return
    progress(message % args if args else message)
