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

    def get_objects_by_sync_token(
        self,
        *,
        sync_token=None,
        load_objects=False,
        disable_fallback=False,
    ):
        return []

    def search(self, *, start, end, event=None, expand=None):
        return [FakeResult()]


class FakeClient:
    def __init__(self, *, url, username, password, timeout=None):
        self.url = url
        self.username = username
        self.password = password
        self.timeout = timeout

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
        "Lark CalDAV search window: start=2026-06-17T10:00:00+00:00 "
        "end=2026-06-17T11:00:00+00:00",
        "Starting Lark CalDAV attempt 1: PROPFIND object listing",
        "Starting Lark CalDAV attempt 2: date range events with recurrence expansion",
        "Lark CalDAV attempt 1: PROPFIND object listing",
        "Lark CalDAV attempt 1 raw results: 0",
        "Lark CalDAV attempt 2: date range events with recurrence expansion",
        "Lark CalDAV attempt 2 raw results: 1",
        "Lark CalDAV selected raw results: 1",
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

        def search(self, *, start, end, event=None, expand=None):
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


def test_list_lark_events_retries_with_more_permissive_search(monkeypatch, tmp_path):
    class FallbackCalendar:
        url = "https://caldav.example.com/calendars/alice/work"

        def __init__(self):
            self.calls = []

        def search(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs == {"start": start, "end": end, "event": True, "expand": True}:
                return []
            if kwargs == {"start": start, "end": end, "event": True, "expand": False}:
                return [FakeResult()]
            raise AssertionError(f"unexpected search kwargs: {kwargs}")

    calendar = FallbackCalendar()

    class FallbackClient(FakeClient):
        def calendar(self, *, url):
            return calendar

    config = CaldavConfig(
        host="https://caldav.example.com",
        username="alice",
        password="secret",
        calendar_url="https://caldav.example.com/calendars/alice/work",
    )
    start = datetime(2026, 6, 17, 10, 0, tzinfo=UTC)
    end = datetime(2026, 6, 17, 11, 0, tzinfo=UTC)
    dump_path = tmp_path / "lark-response.txt"
    messages: list[str] = []

    monkeypatch.setattr("cal_sync.lark_caldav.DAVClient", FallbackClient)

    events = list_lark_events(
        config,
        start,
        end,
        progress=messages.append,
        verbose=True,
        dump_response_path=dump_path,
    )

    assert [event.source_id for event in events] == ["lark-1"]
    assert calendar.calls == [
        {"start": start, "end": end, "event": True, "expand": True},
        {"start": start, "end": end, "event": True, "expand": False},
    ]
    assert "Lark CalDAV attempt 1 raw results: 0" in messages
    assert "Lark CalDAV attempt 2 raw results: 0" in messages
    assert "Lark CalDAV attempt 3 raw results: 1" in messages
    dump = dump_path.read_text(encoding="utf-8")
    assert "attempt: 1" in dump
    assert "event: True" in dump
    assert "expand: True" in dump
    assert "attempt: 2" in dump
    assert "expand: False" in dump


class FakeUrl:
    def __init__(self, value):
        self.value = value.rstrip("/")

    def join(self, href):
        if str(href).startswith("http"):
            return FakeUrl(str(href))
        return FakeUrl(f"{self.value}/{str(href).lstrip('/')}")

    def canonical(self):
        return self.value

    def __str__(self):
        return self.value


class FakePropfindResponse:
    def __init__(self, hrefs):
        self.hrefs = hrefs

    def expand_simple_props(self, props):
        return {href: {} for href in self.hrefs}


def test_list_lark_events_loads_objects_by_propfind_before_search(monkeypatch):
    class PropfindCalendar:
        url = FakeUrl("https://caldav.example.com/calendars/alice/work")

        def __init__(self):
            self.search_called = False
            self.query_properties_args = None

        def _query_properties(self, props, depth):
            self.query_properties_args = {"props": props, "depth": depth}
            return FakePropfindResponse(["lark-1.ics"])

        def event_by_url(self, href):
            assert href == "lark-1.ics"
            return FakeResult()

        def search(self, **kwargs):
            self.search_called = True
            return []

    calendar = PropfindCalendar()

    class PropfindClient(FakeClient):
        def calendar(self, *, url):
            return calendar

    config = CaldavConfig(
        host="https://caldav.example.com",
        username="alice",
        password="secret",
        calendar_url="https://caldav.example.com/calendars/alice/work",
    )

    monkeypatch.setattr("cal_sync.lark_caldav.DAVClient", PropfindClient)

    events = list_lark_events(
        config,
        datetime(2026, 6, 17, 9, 0, tzinfo=UTC),
        datetime(2026, 6, 17, 12, 0, tzinfo=UTC),
    )

    assert [event.source_id for event in events] == ["lark-1"]
    assert calendar.query_properties_args["depth"] == 1
    assert calendar.search_called is False


def test_list_lark_events_prefers_sync_token_object_loading(monkeypatch):
    class SyncCalendar:
        url = "https://caldav.example.com/calendars/alice/work"

        def __init__(self):
            self.search_called = False
            self.sync_kwargs = None

        def get_objects_by_sync_token(
            self,
            *,
            sync_token=None,
            load_objects=False,
            disable_fallback=False,
        ):
            self.sync_kwargs = {
                "sync_token": sync_token,
                "load_objects": load_objects,
                "disable_fallback": disable_fallback,
            }
            return [FakeResult()]

        def search(self, **kwargs):
            self.search_called = True
            return []

    calendar = SyncCalendar()

    class SyncClient(FakeClient):
        def calendar(self, *, url):
            return calendar

    config = CaldavConfig(
        host="https://caldav.example.com",
        username="alice",
        password="secret",
        calendar_url="https://caldav.example.com/calendars/alice/work",
    )

    monkeypatch.setattr("cal_sync.lark_caldav.DAVClient", SyncClient)

    events = list_lark_events(
        config,
        datetime(2026, 6, 17, 9, 0, tzinfo=UTC),
        datetime(2026, 6, 17, 12, 0, tzinfo=UTC),
        use_sync_token=True,
    )

    assert [event.source_id for event in events] == ["lark-1"]
    assert calendar.sync_kwargs == {
        "sync_token": None,
        "load_objects": True,
        "disable_fallback": True,
    }
    assert calendar.search_called is False


def test_list_lark_events_filters_sync_loaded_objects_locally(monkeypatch):
    class OutsideComponent(FakeComponent):
        def __init__(self):
            super().__init__()
            self.uid = FakeText("outside-window")
            self.dtstart = FakeText(datetime(2026, 6, 18, 10, 0, tzinfo=UTC))
            self.dtend = FakeText(datetime(2026, 6, 18, 11, 0, tzinfo=UTC))

    class OutsideVobject:
        def components(self):
            return [OutsideComponent()]

    class OutsideResult(FakeResult):
        vobject_instance = OutsideVobject()

    class SyncCalendar:
        url = "https://caldav.example.com/calendars/alice/work"

        def get_objects_by_sync_token(
            self,
            *,
            sync_token=None,
            load_objects=False,
            disable_fallback=False,
        ):
            return [FakeResult(), OutsideResult()]

        def search(self, **kwargs):
            raise AssertionError("search should not be called when sync-token returns objects")

    class SyncClient(FakeClient):
        def calendar(self, *, url):
            return SyncCalendar()

    config = CaldavConfig(
        host="https://caldav.example.com",
        username="alice",
        password="secret",
        calendar_url="https://caldav.example.com/calendars/alice/work",
    )

    monkeypatch.setattr("cal_sync.lark_caldav.DAVClient", SyncClient)

    events = list_lark_events(
        config,
        datetime(2026, 6, 17, 9, 0, tzinfo=UTC),
        datetime(2026, 6, 17, 12, 0, tzinfo=UTC),
        use_sync_token=True,
    )

    assert [event.source_id for event in events] == ["lark-1"]
