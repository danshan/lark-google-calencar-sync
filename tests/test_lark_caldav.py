from datetime import UTC, datetime

from cal_sync.config import CaldavConfig
from cal_sync.lark_caldav import list_lark_events


class FakeText:
    def __init__(self, value):
        self.value = value


class FakeComponent:
    name = "VEVENT"

    def __init__(self):
        self.uid = FakeText("lark-1")
        self.summary = FakeText("Planning")
        self.description = FakeText("Discuss roadmap")
        self.location = FakeText("Room A")
        self.dtstart = FakeText(datetime(2026, 6, 17, 10, 0, tzinfo=UTC))
        self.dtend = FakeText(datetime(2026, 6, 17, 11, 0, tzinfo=UTC))


class FakeVobject:
    def components(self):
        return [FakeComponent()]


class FakeResult:
    etag = "etag-1"
    vobject_instance = FakeVobject()


class FakeCalendar:
    url = "https://caldav.example.com/calendars/alice/work"

    def search(self, *, start, end, event, expand):
        return [FakeResult()]


class FakeClient:
    def __init__(self, *, url, username, password):
        self.url = url
        self.username = username
        self.password = password

    def calendar(self, *, url):
        return FakeCalendar()


def test_list_lark_events_reports_verbose_details_without_password(monkeypatch):
    messages: list[str] = []
    config = CaldavConfig(
        host="https://caldav.example.com",
        username="alice",
        password="secret",
        calendar_url="https://caldav.example.com/calendars/alice/work",
    )
    start = datetime(2026, 6, 17, 10, 0, tzinfo=UTC)
    end = datetime(2026, 6, 17, 11, 0, tzinfo=UTC)

    monkeypatch.setattr("cal_sync.lark_caldav.DAVClient", FakeClient)

    events = list_lark_events(config, start, end, progress=messages.append, verbose=True)

    assert [event.source_id for event in events] == ["lark-1"]
    assert messages == [
        "Lark CalDAV host: https://caldav.example.com",
        "Lark CalDAV username: alice",
        "Lark CalDAV calendar URL: https://caldav.example.com/calendars/alice/work",
        "Lark CalDAV search: start=2026-06-17T10:00:00+00:00 "
        "end=2026-06-17T11:00:00+00:00 event=True expand=True",
        "Lark CalDAV raw results: 1",
        "Lark event: source_id=lark-1 start=2026-06-17T10:00:00+00:00 "
        "end=2026-06-17T11:00:00+00:00 summary=Planning",
    ]
    assert "secret" not in "\n".join(messages)
