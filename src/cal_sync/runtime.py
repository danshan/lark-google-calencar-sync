from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from cal_sync.config import AppConfig
from cal_sync.google_calendar import apply_sync_plan, build_google_service, list_google_events
from cal_sync.lark_caldav import list_lark_events
from cal_sync.logging_config import configure_logging
from cal_sync.sync import SyncPlan, build_sync_plan

LOGGER = logging.getLogger(__name__)


def sync_once(config: AppConfig) -> SyncPlan:
    configure_logging(config.log_path)
    start, end = sync_window(config.sync.past_days, config.sync.future_days)
    LOGGER.info("Sync started: start=%s end=%s", start.isoformat(), end.isoformat())

    lark_events = list_lark_events(config.caldav, start, end)
    google_service = build_google_service(config.google)
    google_events = list_google_events(google_service, config.google.calendar_id, start, end)
    plan = build_sync_plan(lark_events, google_events)

    LOGGER.info(
        "Sync plan: create=%s update=%s delete=%s dry_run=%s",
        len(plan.to_create),
        len(plan.to_update),
        len(plan.to_delete),
        config.sync.dry_run,
    )
    if not config.sync.dry_run:
        apply_sync_plan(google_service, config.google.calendar_id, plan)
    LOGGER.info("Sync finished")
    return plan


def sync_window(past_days: int, future_days: int) -> tuple[datetime, datetime]:
    now = datetime.now(tz=ZoneInfo("Asia/Shanghai"))
    return now - timedelta(days=past_days), now + timedelta(days=future_days)

