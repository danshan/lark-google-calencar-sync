from __future__ import annotations

from dataclasses import dataclass, field

from cal_sync.models import CalendarEvent


@dataclass(frozen=True)
class SyncPlan:
    to_create: list[CalendarEvent] = field(default_factory=list)
    to_update: list[CalendarEvent] = field(default_factory=list)
    to_delete: list[CalendarEvent] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.to_create or self.to_update or self.to_delete)


def build_sync_plan(
    lark_events: list[CalendarEvent], google_events: list[CalendarEvent]
) -> SyncPlan:
    lark_by_source_id = {event.source_id: event for event in lark_events}
    google_by_source_id = {
        event.source_id: event
        for event in google_events
        if event.google_id is not None and event.source_id != "external"
    }

    to_create: list[CalendarEvent] = []
    to_update: list[CalendarEvent] = []
    to_delete: list[CalendarEvent] = []

    for source_id, lark_event in lark_by_source_id.items():
        google_event = google_by_source_id.get(source_id)
        if google_event is None:
            to_create.append(lark_event)
            continue

        if lark_event.content_key() != google_event.content_key():
            to_update.append(lark_event.model_copy(update={"google_id": google_event.google_id}))

    for source_id, google_event in google_by_source_id.items():
        if source_id not in lark_by_source_id:
            to_delete.append(google_event)

    return SyncPlan(to_create=to_create, to_update=to_update, to_delete=to_delete)

