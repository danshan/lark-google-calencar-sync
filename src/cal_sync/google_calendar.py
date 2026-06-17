from __future__ import annotations

import os
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from cal_sync.config import GoogleConfig
from cal_sync.models import CalendarEvent
from cal_sync.sync import SyncPlan

GOOGLE_SOURCE_KEY = "larkSourceId"
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


class GoogleAuthorizationError(RuntimeError):
    pass


def build_google_service(config: GoogleConfig) -> Any:
    credentials = load_credentials(config.credentials_path, config.token_path)
    return build("calendar", "v3", credentials=credentials)


def load_credentials(credentials_path: Path, token_path: Path) -> Credentials:
    credentials = None
    if token_path.exists():
        credentials = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
        try:
            credentials = flow.run_local_server(port=0)
        except webbrowser.Error:
            credentials = _run_manual_authorization(flow)

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    return credentials


def _run_manual_authorization(flow: InstalledAppFlow) -> Credentials:
    flow.redirect_uri = "http://localhost"
    authorization_url, _ = flow.authorization_url(prompt="consent")
    print("No runnable browser was found on this system.")
    print("Open this URL in a browser on another machine:")
    print(authorization_url)
    print("After Google redirects to localhost, copy the full redirected URL.")
    try:
        authorization_response = input("Paste the full redirected URL: ").strip()
    except EOFError as exc:
        raise GoogleAuthorizationError(
            "Google authorization requires a browser or a pasted redirected URL."
        ) from exc
    if not authorization_response:
        raise GoogleAuthorizationError(
            "Google authorization requires the full redirected URL."
        )
    _validate_manual_authorization_response(authorization_response)
    try:
        _fetch_manual_token(flow, authorization_response)
    except Exception as exc:
        raise GoogleAuthorizationError(
            "Google authorization failed. Paste the full final localhost URL from the browser."
        ) from exc
    return flow.credentials


def _validate_manual_authorization_response(authorization_response: str) -> None:
    parsed = urlparse(authorization_response)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise GoogleAuthorizationError(
            "Google authorization requires the full redirected localhost URL."
        )


def _fetch_manual_token(flow: InstalledAppFlow, authorization_response: str) -> None:
    previous = os.environ.get("OAUTHLIB_INSECURE_TRANSPORT")
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    try:
        flow.fetch_token(authorization_response=authorization_response)
    finally:
        if previous is None:
            os.environ.pop("OAUTHLIB_INSECURE_TRANSPORT", None)
        else:
            os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = previous


def event_to_google_body(event: CalendarEvent) -> dict[str, Any]:
    return {
        "summary": event.summary,
        "description": event.description,
        "location": event.location,
        "start": {"dateTime": event.start.isoformat()},
        "end": {"dateTime": event.end.isoformat()},
        "extendedProperties": {"private": {GOOGLE_SOURCE_KEY: event.source_id}},
    }


def google_item_to_event(item: dict[str, Any]) -> CalendarEvent:
    source_id = (
        item.get("extendedProperties", {}).get("private", {}).get(GOOGLE_SOURCE_KEY, "external")
    )
    return CalendarEvent(
        source_id=source_id,
        google_id=item["id"],
        summary=item.get("summary", ""),
        description=item.get("description", ""),
        location=item.get("location", ""),
        start=_parse_google_datetime(item["start"]),
        end=_parse_google_datetime(item["end"]),
        updated_at=_parse_optional_datetime(item.get("updated")),
        etag=item.get("etag"),
    )


def list_google_events(
    service: Any,
    calendar_id: str,
    start: datetime,
    end: datetime,
) -> list[CalendarEvent]:
    items: list[dict[str, Any]] = []
    page_token = None
    while True:
        response = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                showDeleted=False,
                pageToken=page_token,
            )
            .execute()
        )
        items.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return [google_item_to_event(item) for item in items]


def apply_sync_plan(service: Any, calendar_id: str, plan: SyncPlan) -> None:
    events = service.events()
    for event in plan.to_create:
        events.insert(calendarId=calendar_id, body=event_to_google_body(event)).execute()
    for event in plan.to_update:
        if event.google_id is None:
            raise ValueError("Google event id is required for update")
        events.patch(
            calendarId=calendar_id,
            eventId=event.google_id,
            body=event_to_google_body(event),
        ).execute()
    for event in plan.to_delete:
        if event.google_id is None:
            raise ValueError("Google event id is required for delete")
        events.delete(calendarId=calendar_id, eventId=event.google_id).execute()


def _parse_google_datetime(value: dict[str, str]) -> datetime:
    raw = value.get("dateTime") or value.get("date")
    if raw is None:
        raise ValueError(f"Google event time is missing: {value}")
    return _parse_datetime(raw)


def _parse_optional_datetime(raw: str | None) -> datetime | None:
    return _parse_datetime(raw) if raw else None


def _parse_datetime(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))
