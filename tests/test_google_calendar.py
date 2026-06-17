from datetime import UTC, datetime

from cal_sync.google_calendar import (
    GOOGLE_SOURCE_KEY,
    event_to_google_body,
    google_item_to_event,
)
from cal_sync.models import CalendarEvent


def test_event_to_google_body_marks_lark_source_id():
    event = CalendarEvent(
        source_id="lark-123",
        summary="Focus",
        description="Deep work",
        location="Home",
        start=datetime(2026, 6, 17, 10, 0, tzinfo=UTC),
        end=datetime(2026, 6, 17, 11, 0, tzinfo=UTC),
    )

    body = event_to_google_body(event)

    assert body["summary"] == "Focus"
    assert body["extendedProperties"]["private"][GOOGLE_SOURCE_KEY] == "lark-123"
    assert body["start"]["dateTime"] == "2026-06-17T10:00:00+00:00"
    assert body["end"]["dateTime"] == "2026-06-17T11:00:00+00:00"


def test_google_item_to_event_returns_external_without_source_marker():
    item = {
        "id": "google-1",
        "summary": "Personal",
        "start": {"dateTime": "2026-06-17T10:00:00+00:00"},
        "end": {"dateTime": "2026-06-17T11:00:00+00:00"},
    }

    event = google_item_to_event(item)

    assert event.source_id == "external"
    assert event.google_id == "google-1"
