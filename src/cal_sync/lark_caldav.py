from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from caldav import DAVClient
from caldav.elements import dav
from caldav.lib import error as caldav_error
from dateutil.parser import isoparse

from cal_sync.config import CaldavConfig
from cal_sync.models import CalendarEvent

LOGGER = logging.getLogger(__name__)
ProgressReporter = Callable[[str], None]
SearchAttempt = tuple[str, dict[str, object]]


def list_lark_calendars(config: CaldavConfig) -> list[tuple[str, str]]:
    with DAVClient(
        url=config.host,
        username=config.username,
        password=config.password,
        timeout=config.timeout_seconds,
    ) as client:
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
    use_sync_token: bool = True,
) -> list[CalendarEvent]:
    attempts = _search_attempts(start, end)
    if verbose:
        _report(progress, "Lark CalDAV host: %s", config.host)
        _report(progress, "Lark CalDAV username: %s", config.username)
        _report(progress, "Lark CalDAV calendar URL: %s", config.calendar_url or "<first calendar>")
        _report(
            progress,
            "Lark CalDAV search window: start=%s end=%s",
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
    attempt_results = []
    start_index = 1
    if use_sync_token:
        if verbose:
            _report(progress, "Starting Lark CalDAV attempt 1: sync-token object loading")
        sync_attempt_result = _load_lark_objects_by_sync_token(calendar)
        attempt_results.append(sync_attempt_result)
        start_index = 2

    if attempt_results and attempt_results[-1][2]:
        results = attempt_results[-1][2]
    else:
        if verbose:
            _report(
                progress,
                "Starting Lark CalDAV attempt %s: PROPFIND object listing",
                start_index,
            )
        propfind_attempt_result = _load_lark_objects_by_propfind(calendar)
        attempt_results.append(propfind_attempt_result)
        start_index += 1

        if propfind_attempt_result[2]:
            results = propfind_attempt_result[2]
        else:
            search_attempt_results = _search_lark_calendar(
                calendar,
                attempts,
                progress=progress,
                verbose=verbose,
                start_index=start_index,
            )
            attempt_results.extend(search_attempt_results)
            results = search_attempt_results[-1][2] if search_attempt_results else []
    if dump_response_path is not None:
        _dump_lark_response(
            dump_response_path,
            config=config,
            start=start,
            end=end,
            attempt_results=attempt_results,
        )
        _report(progress, "Wrote raw Lark CalDAV response dump to %s", dump_response_path)

    for index, (label, parameters, attempt_items) in enumerate(attempt_results, start=1):
        LOGGER.info(
            "Lark CalDAV attempt %s: label=%s parameters=%s raw_count=%s",
            index,
            label,
            _format_search_parameters(parameters),
            len(attempt_items),
        )
        if verbose:
            _report(progress, "Lark CalDAV attempt %s: %s", index, label)
            _report(progress, "Lark CalDAV attempt %s raw results: %s", index, len(attempt_items))

    LOGGER.info("Lark CalDAV selected raw results: count=%s", len(results))
    if verbose:
        _report(progress, "Lark CalDAV selected raw results: %s", len(results))

    events = _caldav_results_to_events(
        results,
        start,
        end,
        progress=progress,
        verbose=verbose,
    )
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
            _report_event_detail(progress, event)
    return events


def _get_calendar(config: CaldavConfig) -> Any:
    client = DAVClient(
        url=config.host,
        username=config.username,
        password=config.password,
        timeout=config.timeout_seconds,
    )
    if config.calendar_url:
        return client.calendar(url=config.calendar_url)
    calendars = client.principal().get_calendars()
    if not calendars:
        raise RuntimeError("No Lark CalDAV calendars found")
    return calendars[0]


def _caldav_results_to_events(
    results: list[Any],
    start: datetime,
    end: datetime,
    *,
    progress: ProgressReporter | None,
    verbose: bool,
) -> list[CalendarEvent]:
    events = []
    outside_window_count = 0
    for result in results:
        event, skip_reason = _caldav_result_to_event(result)
        if event is None:
            _report_skipped_object(progress, verbose, result, skip_reason or "unparsed object")
            continue
        if not _event_overlaps_window(event, start, end):
            outside_window_count += 1
            LOGGER.debug(
                "Skipped Lark CalDAV object outside sync window: source_id=%s identity=%s",
                event.source_id,
                _result_identity(result),
            )
            continue
        events.append(event)
    if outside_window_count:
        LOGGER.info(
            "Skipped Lark CalDAV objects outside sync window: count=%s",
            outside_window_count,
        )
        if verbose:
            _report(
                progress,
                "Skipped Lark CalDAV objects outside sync window: %s",
                outside_window_count,
            )
    return events


def _caldav_result_to_event(result: Any) -> tuple[CalendarEvent | None, str | None]:
    vobject_instance = _safe_attr(result, "vobject_instance")
    if vobject_instance is None:
        return None, "missing vobject_instance"
    components = getattr(vobject_instance, "components", None)
    if not callable(components):
        return None, "vobject_instance has no components"
    try:
        component = next((item for item in components() if item.name == "VEVENT"), None)
    except Exception as exc:
        return None, f"component iteration failed: {exc}"
    if component is None:
        return None, "missing VEVENT component"
    try:
        uid = str(component.uid.value)
        return (
            CalendarEvent(
                source_id=uid,
                summary=_component_text(component, "summary"),
                description=_component_text(component, "description"),
                location=_component_text(component, "location"),
                start=_as_datetime(component.dtstart.value),
                end=_as_datetime(component.dtend.value),
                updated_at=_optional_datetime(getattr(component, "last_modified", None)),
                etag=_safe_attr(result, "etag"),
            ),
            None,
        )
    except Exception as exc:
        return None, f"VEVENT parse failed: {exc}"


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


def _event_overlaps_window(event: CalendarEvent, start: datetime, end: datetime) -> bool:
    return event.end > start and event.start < end


def _load_lark_objects_by_sync_token(calendar: Any) -> tuple[str, dict[str, object], list[Any]]:
    parameters = {
        "sync_token": None,
        "load_objects": True,
        "disable_fallback": True,
    }
    try:
        collection = calendar.get_objects_by_sync_token(**parameters)
    except (caldav_error.ReportError, caldav_error.DAVError, AttributeError) as exc:
        LOGGER.info("Lark CalDAV sync-token object loading failed: %s", exc)
        return ("sync-token object loading", parameters, [])
    return ("sync-token object loading", parameters, list(collection))


def _load_lark_objects_by_propfind(calendar: Any) -> tuple[str, dict[str, object], list[Any]]:
    parameters = {"depth": 1, "props": "getetag"}
    try:
        response = calendar._query_properties([dav.GetEtag()], depth=1)
        href_props = response.expand_simple_props([dav.GetEtag()])
        objects = []
        for href in href_props:
            if str(calendar.url.join(href).canonical()) == str(calendar.url.canonical()):
                continue
            try:
                objects.append(calendar.event_by_url(href))
            except (caldav_error.NotFoundError, caldav_error.DAVError, ValueError) as exc:
                LOGGER.info("Lark CalDAV PROPFIND object load skipped: href=%s error=%s", href, exc)
        return ("PROPFIND object listing", parameters, objects)
    except (caldav_error.ReportError, caldav_error.DAVError, AttributeError) as exc:
        LOGGER.info("Lark CalDAV PROPFIND object listing failed: %s", exc)
        return ("PROPFIND object listing", parameters, [])


def _search_attempts(start: datetime, end: datetime) -> list[SearchAttempt]:
    return [
        (
            "date range events with recurrence expansion",
            {"start": start, "end": end, "event": True, "expand": True},
        ),
        (
            "date range events without recurrence expansion",
            {"start": start, "end": end, "event": True, "expand": False},
        ),
        (
            "date range without component or expansion filters",
            {"start": start, "end": end},
        ),
    ]


def _search_lark_calendar(
    calendar: Any,
    attempts: list[SearchAttempt],
    *,
    progress: ProgressReporter | None = None,
    verbose: bool = False,
    start_index: int = 1,
) -> list[tuple[str, dict[str, object], list[Any]]]:
    attempt_results: list[tuple[str, dict[str, object], list[Any]]] = []
    for offset, (label, parameters) in enumerate(attempts):
        attempt_index = start_index + offset
        if verbose:
            _report(progress, "Starting Lark CalDAV attempt %s: %s", attempt_index, label)
        try:
            results = calendar.search(**parameters)
        except Exception as exc:
            LOGGER.info("Lark CalDAV search attempt failed: label=%s error=%s", label, exc)
            results = []
        attempt_results.append((label, parameters, results))
        if results:
            break
    return attempt_results


def _dump_lark_response(
    path: Path,
    *,
    config: CaldavConfig,
    start: datetime,
    end: datetime,
    attempt_results: list[tuple[str, dict[str, object], list[Any]]],
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
        "",
        "## Response",
        f"attempt_count: {len(attempt_results)}",
    ]
    selected_results = attempt_results[-1][2] if attempt_results else []
    lines.append(f"raw_result_count: {len(selected_results)}")
    if not selected_results:
        lines.append("No CalDAV object resources were returned by calendar.search().")

    for attempt_index, (label, parameters, results) in enumerate(attempt_results, start=1):
        lines.extend(
            [
                "",
                f"## Attempt {attempt_index}",
                f"attempt: {attempt_index}",
                f"label: {label}",
                f"raw_result_count: {len(results)}",
                "parameters:",
                _format_search_parameters(parameters),
            ]
        )
        for result_index, result in enumerate(results, start=1):
            lines.extend(
                [
                    "",
                    f"### Attempt {attempt_index} Result {result_index}",
                    f"type: {type(result).__module__}.{type(result).__qualname__}",
                ]
            )
            _append_attr(lines, result, "url")
            _append_attr(lines, result, "etag")
            _append_attr(lines, result, "id")
            _append_attr(lines, result, "canonical_url")
            _append_attr(lines, result, "data")
            vobject_instance = _safe_attr(result, "vobject_instance")
            if vobject_instance is not None:
                lines.extend(["", "#### vobject_instance.serialize()"])
                serialize = getattr(vobject_instance, "serialize", None)
                if callable(serialize):
                    lines.append(str(serialize()))
                else:
                    lines.append(str(vobject_instance))
            else:
                lines.extend(["", "#### vobject_instance", "<missing>"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _format_search_parameters(parameters: dict[str, object]) -> str:
    lines = []
    for key, value in parameters.items():
        rendered = value.isoformat() if isinstance(value, datetime) else str(value)
        lines.append(f"{key}: {rendered}")
    return "\n".join(lines)


def _append_attr(lines: list[str], result: Any, name: str) -> None:
    value = _safe_attr(result, name)
    if value is None:
        return
    if name == "data":
        lines.extend(["", "### data", str(value)])
    else:
        lines.append(f"{name}: {value}")


def _safe_attr(result: Any, name: str) -> Any:
    try:
        return getattr(result, name)
    except Exception as exc:
        LOGGER.info(
            "Lark CalDAV object attribute read failed: identity=%s attr=%s error=%s",
            _result_identity(result),
            name,
            exc,
        )
        return None


def _report_skipped_object(
    progress: ProgressReporter | None,
    verbose: bool,
    result: Any,
    reason: str,
) -> None:
    identity = _result_identity(result)
    LOGGER.info("Skipped Lark CalDAV object: reason=%s identity=%s", reason, identity)
    if verbose:
        _report(progress, "Skipped Lark CalDAV object: reason=%s identity=%s", reason, identity)


def _result_identity(result: Any) -> str:
    for name in ("url", "id", "canonical_url", "etag"):
        value = _safe_attr_without_logging(result, name)
        if value:
            return f"{name}={value}"
    return f"type={type(result).__module__}.{type(result).__qualname__}"


def _safe_attr_without_logging(result: Any, name: str) -> Any:
    try:
        return getattr(result, name)
    except Exception:
        return None


def _report_event_detail(progress: ProgressReporter | None, event: CalendarEvent) -> None:
    _report(progress, "Lark event detail:")
    _report(progress, "  title: %s", _display_value(event.summary))
    _report(progress, "  start: %s", event.start.isoformat())
    _report(progress, "  end: %s", event.end.isoformat())
    _report(progress, "  location: %s", _display_value(event.location))
    _report(progress, "  source_id: %s", event.source_id)


def _display_value(value: str) -> str:
    return value if value else "<empty>"


def _report(progress: ProgressReporter | None, message: str, *args: object) -> None:
    if progress is None:
        return
    progress(message % args if args else message)
