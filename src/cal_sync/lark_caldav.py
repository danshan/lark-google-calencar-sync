from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from caldav import DAVClient
from dateutil.parser import isoparse

from cal_sync.config import CaldavConfig
from cal_sync.models import CalendarEvent

LOGGER = logging.getLogger(__name__)
ProgressReporter = Callable[[str], None]


def list_lark_calendars(config: CaldavConfig) -> list[tuple[str, str]]:
    with DAVClient(url=config.host, username=config.username, password=config.password) as client:
        principal = client.principal()
        calendars = principal.get_calendars()
        return [(calendar.get_display_name(), str(calendar.url)) for calendar in calendars]


def list_lark_events(
    config: CaldavConfig,
    start: datetime,
    end: datetime,
    *,
    progress: ProgressReporter | None = None,
    verbose: bool = False,
) -> list[CalendarEvent]:
    if verbose:
        _report(progress, "Lark CalDAV host: %s", config.host)
        _report(progress, "Lark CalDAV username: %s", config.username)
        _report(progress, "Lark CalDAV calendar URL: %s", config.calendar_url or "<first calendar>")
        _report(
            progress,
            "Lark CalDAV search: start=%s end=%s event=True expand=True",
            start.isoformat(),
            end.isoformat(),
        )
    LOGGER.info(
        "Lark CalDAV search: host=%s username=%s calendar_url=%s start=%s end=%s",
        config.host,
        config.username,
        config.calendar_url or "<first calendar>",
        start.isoformat(),
        end.isoformat(),
    )

    calendar = _get_calendar(config)
    results = calendar.search(start=start, end=end, event=True, expand=True)
    LOGGER.info("Lark CalDAV raw results: count=%s", len(results))
    if verbose:
        _report(progress, "Lark CalDAV raw results: %s", len(results))

    events = [_caldav_result_to_event(result) for result in results]
    if verbose and not events:
        _report(progress, "No Lark events returned by CalDAV search.")
    for event in events:
        LOGGER.info(
            "Lark event: source_id=%s start=%s end=%s summary=%s",
            event.source_id,
            event.start.isoformat(),
            event.end.isoformat(),
            event.summary,
        )
        if verbose:
            _report(
                progress,
                "Lark event: source_id=%s start=%s end=%s summary=%s",
                event.source_id,
                event.start.isoformat(),
                event.end.isoformat(),
                event.summary,
            )
    return events


def _get_calendar(config: CaldavConfig) -> Any:
    client = DAVClient(url=config.host, username=config.username, password=config.password)
    if config.calendar_url:
        return client.calendar(url=config.calendar_url)
    calendars = client.principal().get_calendars()
    if not calendars:
        raise RuntimeError("No Lark CalDAV calendars found")
    return calendars[0]


def _caldav_result_to_event(result: Any) -> CalendarEvent:
    vobject_instance = result.vobject_instance
    component = next(item for item in vobject_instance.components() if item.name == "VEVENT")
    uid = str(component.uid.value)
    return CalendarEvent(
        source_id=uid,
        summary=_component_text(component, "summary"),
        description=_component_text(component, "description"),
        location=_component_text(component, "location"),
        start=_as_datetime(component.dtstart.value),
        end=_as_datetime(component.dtend.value),
        updated_at=_optional_datetime(getattr(component, "last_modified", None)),
        etag=getattr(result, "etag", None),
    )


def _component_text(component: Any, name: str) -> str:
    value = getattr(component, name, None)
    return str(value.value) if value is not None else ""


def _optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    return _as_datetime(value.value)


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return isoparse(str(value))


def _report(progress: ProgressReporter | None, message: str, *args: object) -> None:
    if progress is None:
        return
    progress(message % args if args else message)
