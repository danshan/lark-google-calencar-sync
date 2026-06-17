from datetime import UTC, datetime

from cal_sync.models import CalendarEvent
from cal_sync.sync import build_sync_plan


def event(
    source_id: str,
    *,
    google_id: str | None = None,
    summary: str = "Planning",
    updated_at: datetime | None = None,
) -> CalendarEvent:
    instant = updated_at or datetime(2026, 6, 17, 9, 0, tzinfo=UTC)
    return CalendarEvent(
        source_id=source_id,
        google_id=google_id,
        summary=summary,
        description="",
        location="",
        start=datetime(2026, 6, 17, 10, 0, tzinfo=UTC),
        end=datetime(2026, 6, 17, 11, 0, tzinfo=UTC),
        updated_at=instant,
        etag="etag",
    )


def test_build_sync_plan_creates_updates_and_deletes_only_managed_google_events():
    lark_events = [
        event("lark-1", summary="New event"),
        event("lark-2", summary="Updated event"),
    ]
    google_events = [
        event("lark-2", google_id="google-2", summary="Old title"),
        event("lark-3", google_id="google-3", summary="Removed from Lark"),
        event("external", google_id="personal-1", summary="Personal"),
    ]

    plan = build_sync_plan(lark_events, google_events)

    assert [item.source_id for item in plan.to_create] == ["lark-1"]
    assert [(item.google_id, item.summary) for item in plan.to_update] == [
        ("google-2", "Updated event")
    ]
    assert [item.google_id for item in plan.to_delete] == ["google-3"]


def test_build_sync_plan_ignores_equal_events():
    lark_event = event("lark-1", summary="Same")
    google_event = event("lark-1", google_id="google-1", summary="Same")

    plan = build_sync_plan([lark_event], [google_event])

    assert plan.to_create == []
    assert plan.to_update == []
    assert plan.to_delete == []
