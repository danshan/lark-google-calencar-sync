from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from caldav import DAVClient
from caldav.lib import error as caldav_error
from dateutil.parser import isoparse
from dateutil.rrule import rrulestr

from cal_sync.config import CaldavConfig
from cal_sync.models import CalendarEvent

LOGGER = logging.getLogger(__name__)
ProgressReporter = Callable[[str], None]
AttemptResult = tuple[str, dict[str, object], list[Any]]
LARK_STATE_SCHEMA_VERSION = 4


class LarkCaldavAuthenticationError(RuntimeError):
    pass


def list_lark_calendars(config: CaldavConfig) -> list[tuple[str, str]]:
    try:
        with DAVClient(
            url=config.host,
            username=config.username,
            password=config.password,
            timeout=config.timeout_seconds,
        ) as client:
            principal = client.principal()
            calendars = principal.get_calendars()
            return [(calendar.get_display_name(), str(calendar.url)) for calendar in calendars]
    except caldav_error.AuthorizationError as exc:
        raise LarkCaldavAuthenticationError(
            "Lark CalDAV authorization failed. Check host, username, and password."
        ) from exc


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
    state = _load_lark_state(config.state_path)
    if verbose:
        _report(progress, "Starting Lark CalDAV attempt 1: sync-token object loading")
        _report(
            progress,
            "Lark CalDAV sync token: %s",
            "<empty>" if state.sync_token is None else "<cached>",
        )
    label, parameters, results, next_sync_token = _load_lark_objects_by_sync_token(
        calendar,
        state.sync_token,
    )
    attempt_results: list[AttemptResult] = [(label, parameters, results)]
    if not results:
        if verbose:
            _report(progress, "Starting Lark CalDAV attempt 2: full object fallback")
        label, parameters, results = _load_lark_objects_by_full_collection(calendar)
        attempt_results.append((label, parameters, results))

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

    _apply_lark_results_to_state(
        results,
        state,
        progress=progress,
        verbose=verbose,
    )
    if next_sync_token is not None:
        state.sync_token = next_sync_token
    _save_lark_state(config.state_path, state)

    events = _events_in_window(
        state.events_by_url.values(),
        start,
        end,
        progress=progress,
        verbose=verbose,
    )
    if verbose and not events:
        _report(progress, "No Lark events in sync window.")
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
    try:
        calendars = client.principal().get_calendars()
    except caldav_error.AuthorizationError as exc:
        raise LarkCaldavAuthenticationError(
            "Lark CalDAV authorization failed. Check host, username, and password."
        ) from exc
    if not calendars:
        raise RuntimeError("No Lark CalDAV calendars found")
    return calendars[0]


class LarkState:
    def __init__(
        self,
        *,
        sync_token: str | None = None,
        events_by_url: dict[str, CalendarEvent] | None = None,
    ) -> None:
        self.sync_token = sync_token
        self.events_by_url = events_by_url or {}


def _load_lark_state(path: Path | None) -> LarkState:
    if path is None:
        return LarkState()
    if not path.exists():
        return LarkState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.info(
            "Lark state load failed, starting from empty state: path=%s error=%s",
            path,
            exc,
        )
        return LarkState()
    raw_events = data.get("events_by_url", {})
    if data.get("schema_version") != LARK_STATE_SCHEMA_VERSION:
        LOGGER.info(
            "Lark state schema changed, starting from empty state: path=%s",
            path,
        )
        return LarkState()
    events_by_url = {}
    if isinstance(raw_events, dict):
        for url, event_data in raw_events.items():
            try:
                events_by_url[str(url)] = CalendarEvent.model_validate(event_data)
            except Exception as exc:
                LOGGER.info("Skipped invalid cached Lark event: url=%s error=%s", url, exc)
    sync_token = data.get("sync_token")
    return LarkState(
        sync_token=str(sync_token) if sync_token else None,
        events_by_url=events_by_url,
    )


def _save_lark_state(path: Path | None, state: LarkState) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": LARK_STATE_SCHEMA_VERSION,
        "sync_token": state.sync_token,
        "events_by_url": {
            url: event.model_dump(mode="json")
            for url, event in sorted(state.events_by_url.items())
        },
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _apply_lark_results_to_state(
    results: list[Any],
    state: LarkState,
    *,
    progress: ProgressReporter | None,
    verbose: bool,
) -> None:
    for result in results:
        url = _result_url(result)
        event, skip_reason = _caldav_result_to_event(result)
        if event is None:
            if (
                url is not None
                and url in state.events_by_url
                and skip_reason == "missing vobject_instance"
            ):
                del state.events_by_url[url]
                LOGGER.info("Removed cached Lark event: url=%s", url)
                if verbose:
                    _report(progress, "Removed cached Lark event: url=%s", url)
            else:
                _report_skipped_object(progress, verbose, result, skip_reason or "unparsed object")
            continue
        if url is None:
            _report_skipped_object(progress, verbose, result, "missing object URL")
            continue
        state.events_by_url[url] = event


def _events_in_window(
    events: Any,
    start: datetime,
    end: datetime,
    *,
    progress: ProgressReporter | None,
    verbose: bool,
) -> list[CalendarEvent]:
    window_events = []
    outside_window_count = 0
    for event in events:
        expanded_events = _expand_event_in_window(event, start, end)
        if not expanded_events:
            outside_window_count += 1
            continue
        window_events.extend(expanded_events)
    if outside_window_count:
        LOGGER.info(
            "Skipped cached Lark events outside sync window: count=%s",
            outside_window_count,
        )
        if verbose:
            _report(
                progress,
                "Skipped cached Lark events outside sync window: %s",
                outside_window_count,
            )
    return sorted(window_events, key=lambda event: (event.start, event.end, event.source_id))


def _expand_event_in_window(
    event: CalendarEvent,
    start: datetime,
    end: datetime,
) -> list[CalendarEvent]:
    if not event.recurrence_rule:
        return [event] if _event_overlaps_window(event, start, end) else []

    duration = event.end - event.start
    try:
        recurrence = rrulestr(event.recurrence_rule, dtstart=event.start)
        occurrences = recurrence.between(start - duration, end, inc=True)
    except Exception as exc:
        LOGGER.info(
            "Failed to expand recurring Lark event: source_id=%s rule=%s error=%s",
            event.source_id,
            event.recurrence_rule,
            exc,
        )
        return [event] if _event_overlaps_window(event, start, end) else []

    expanded_events = []
    for occurrence_start in occurrences:
        occurrence_end = occurrence_start + duration
        occurrence = event.model_copy(
            update={
                "source_id": f"{event.source_id}:{occurrence_start.isoformat()}",
                "start": occurrence_start,
                "end": occurrence_end,
            }
        )
        if _event_overlaps_window(occurrence, start, end):
            expanded_events.append(occurrence)
    return expanded_events


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
                recurrence_rule=_component_optional_text(component, "rrule"),
            ),
            None,
        )
    except Exception as exc:
        return None, f"VEVENT parse failed: {exc}"


def _component_text(component: Any, name: str) -> str:
    return _component_optional_text(component, name) or ""


def _component_optional_text(component: Any, name: str) -> str | None:
    value = getattr(component, name, None)
    return str(value.value) if value is not None else None


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


def _load_lark_objects_by_sync_token(
    calendar: Any,
    sync_token: str | None,
) -> tuple[str, dict[str, object], list[Any], str | None]:
    parameters = {
        "sync_token": sync_token,
        "load_objects": True,
        "disable_fallback": True,
    }
    try:
        collection = calendar.get_objects_by_sync_token(**parameters)
    except caldav_error.AuthorizationError as exc:
        raise LarkCaldavAuthenticationError(
            "Lark CalDAV authorization failed. Check host, username, and password."
        ) from exc
    except (caldav_error.ReportError, caldav_error.DAVError, AttributeError) as exc:
        LOGGER.info("Lark CalDAV sync-token object loading failed: %s", exc)
        return ("sync-token object loading", parameters, [], None)
    return (
        "sync-token object loading",
        parameters,
        list(collection),
        getattr(collection, "sync_token", None),
    )


def _load_lark_objects_by_full_collection(
    calendar: Any,
) -> tuple[str, dict[str, object], list[Any]]:
    parameters = {
        "load_objects": True,
        "disable_fallback": False,
    }
    try:
        return ("full object fallback", parameters, list(calendar.get_objects(**parameters)))
    except caldav_error.AuthorizationError as exc:
        raise LarkCaldavAuthenticationError(
            "Lark CalDAV authorization failed. Check host, username, and password."
        ) from exc
    except (caldav_error.ReportError, caldav_error.DAVError, AttributeError) as exc:
        LOGGER.info("Lark CalDAV full object fallback failed: %s", exc)
        return ("full object fallback", parameters, [])


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
        lines.append("No CalDAV object resources were returned by sync-token object loading.")

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


def _result_url(result: Any) -> str | None:
    value = _safe_attr_without_logging(result, "url")
    return _normalize_url(str(value)) if value else None


def _normalize_url(value: str) -> str:
    parsed = urlsplit(value)
    netloc = parsed.netloc
    if (parsed.scheme, parsed.port) in {("https", 443), ("http", 80)}:
        netloc = parsed.hostname or parsed.netloc
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


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
