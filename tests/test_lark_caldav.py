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

    def serialize(self):
        return (
            "BEGIN:VCALENDAR\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:lark-1\r\n"
            "SUMMARY:Planning\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )


class FakeResult:
    etag = "etag-1"
    url = "https://caldav.example.com/calendars/alice/work/lark-1.ics"
    data = "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:lark-1\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
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


def test_list_lark_events_dumps_raw_response(monkeypatch, tmp_path):
    config = CaldavConfig(
        host="https://caldav.example.com",
        username="alice",
        password="secret",
        calendar_url="https://caldav.example.com/calendars/alice/work",
    )
    start = datetime(2026, 6, 17, 10, 0, tzinfo=UTC)
    end = datetime(2026, 6, 17, 11, 0, tzinfo=UTC)
    dump_path = tmp_path / "lark-response.txt"

    monkeypatch.setattr("cal_sync.lark_caldav.DAVClient", FakeClient)

    list_lark_events(config, start, end, dump_response_path=dump_path)

    dump = dump_path.read_text(encoding="utf-8")
    assert "host: https://caldav.example.com" in dump
    assert "username: alice" in dump
    assert "password:" not in dump
    assert "calendar_url: https://caldav.example.com/calendars/alice/work" in dump
    assert "raw_result_count: 1" in dump
    assert "url: https://caldav.example.com/calendars/alice/work/lark-1.ics" in dump
    assert "etag: etag-1" in dump
    assert "BEGIN:VCALENDAR" in dump
    assert "SUMMARY:Planning" in dump


def test_list_lark_events_dumps_zero_result_response(monkeypatch, tmp_path):
    class EmptyCalendar:
        url = "https://caldav.example.com/calendars/alice/work"

        def search(self, *, start, end, event, expand):
            return []

    class EmptyClient(FakeClient):
        def calendar(self, *, url):
            return EmptyCalendar()

    config = CaldavConfig(
        host="https://caldav.example.com",
        username="alice",
        password="secret",
        calendar_url="https://caldav.example.com/calendars/alice/work",
    )
    start = datetime(2026, 6, 17, 10, 0, tzinfo=UTC)
    end = datetime(2026, 6, 17, 11, 0, tzinfo=UTC)
    dump_path = tmp_path / "lark-response.txt"

    monkeypatch.setattr("cal_sync.lark_caldav.DAVClient", EmptyClient)

    list_lark_events(config, start, end, dump_response_path=dump_path)

    dump = dump_path.read_text(encoding="utf-8")
    assert "raw_result_count: 0" in dump
    assert "No CalDAV object resources were returned by calendar.search()." in dump
