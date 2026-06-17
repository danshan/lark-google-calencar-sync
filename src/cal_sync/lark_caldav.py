from __future__ import annotations

from datetime import datetime
from typing import Any

from caldav import DAVClient
from dateutil.parser import isoparse

from cal_sync.config import CaldavConfig
from cal_sync.models import CalendarEvent


def list_lark_calendars(config: CaldavConfig) -> list[tuple[str, str]]:
    with DAVClient(url=config.host, username=config.username, password=config.password) as client:
        principal = client.principal()
        calendars = principal.get_calendars()
        return [(calendar.get_display_name(), str(calendar.url)) for calendar in calendars]


def list_lark_events(
    config: CaldavConfig,
    start: datetime,
    end: datetime,
) -> list[CalendarEvent]:
    calendar = _get_calendar(config)
    results = calendar.search(start=start, end=end, event=True, expand=True)
    return [_caldav_result_to_event(result) for result in results]


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
