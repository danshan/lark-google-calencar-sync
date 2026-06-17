from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CalendarEvent(BaseModel):
    source_id: str
    google_id: str | None = None
    summary: str
    description: str = ""
    location: str = ""
    start: datetime
    end: datetime
    updated_at: datetime | None = None
    etag: str | None = None

    @property
    def is_managed_google_event(self) -> bool:
        return self.google_id is not None and self.source_id != "external"

    def content_key(self) -> tuple[object, ...]:
        return (
            self.summary,
            self.description,
            self.location,
            self.start,
            self.end,
        )

