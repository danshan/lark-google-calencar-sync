from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
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
    dump_response_path: Path | None = None,
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
    if dump_response_path is not None:
        _dump_lark_response(
            dump_response_path,
            config=config,
            start=start,
            end=end,
            results=results,
        )
        _report(progress, "Wrote raw Lark CalDAV response dump to %s", dump_response_path)
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


def _dump_lark_response(
    path: Path,
    *,
    config: CaldavConfig,
    start: datetime,
    end: datetime,
    results: list[Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Lark CalDAV response dump",
        "",
        "## Request",
        f"host: {config.host}",
        f"username: {config.username}",
        f"calendar_url: {config.calendar_url or '<first calendar>'}",
        f"start: {start.isoformat()}",
        f"end: {end.isoformat()}",
        "event: True",
        "expand: True",
        "",
        "## Response",
        f"raw_result_count: {len(results)}",
    ]
    if not results:
        lines.append("No CalDAV object resources were returned by calendar.search().")

    for index, result in enumerate(results, start=1):
        lines.extend(
            [
                "",
                f"## Result {index}",
                f"type: {type(result).__module__}.{type(result).__qualname__}",
            ]
        )
        _append_attr(lines, result, "url")
        _append_attr(lines, result, "etag")
        _append_attr(lines, result, "id")
        _append_attr(lines, result, "canonical_url")
        _append_attr(lines, result, "data")
        vobject_instance = getattr(result, "vobject_instance", None)
        if vobject_instance is not None:
            lines.extend(["", "### vobject_instance.serialize()"])
            serialize = getattr(vobject_instance, "serialize", None)
            if callable(serialize):
                lines.append(str(serialize()))
            else:
                lines.append(str(vobject_instance))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _append_attr(lines: list[str], result: Any, name: str) -> None:
    if not hasattr(result, name):
        return
    value = getattr(result, name)
    if name == "data":
        lines.extend(["", "### data", str(value)])
    else:
        lines.append(f"{name}: {value}")


def _report(progress: ProgressReporter | None, message: str, *args: object) -> None:
    if progress is None:
        return
    progress(message % args if args else message)
