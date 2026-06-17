import json
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


class FakeSyncCollection:
    def __init__(self, objects, sync_token="sync-token-1"):
        self.objects = objects
        self.sync_token = sync_token

    def __iter__(self):
        return iter(self.objects)

    def __len__(self):
        return len(self.objects)


class FakeCalendar:
    url = "https://caldav.example.com/calendars/alice/work"

    def get_objects_by_sync_token(
        self,
        *,
        sync_token=None,
        load_objects=False,
        disable_fallback=False,
    ):
        return FakeSyncCollection([FakeResult()])

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
        "Starting Lark CalDAV attempt 1: sync-token object loading",
        "Lark CalDAV sync token: <empty>",
        "Lark CalDAV attempt 1: sync-token object loading",
        "Lark CalDAV attempt 1 raw results: 1",
        "Lark CalDAV selected raw results: 1",
        "Lark event: source_id=lark-1 start=2026-06-17T10:00:00+00:00 "
        "end=2026-06-17T11:00:00+00:00 summary=Planning",
        "Lark event detail:",
        "  title: Planning",
        "  start: 2026-06-17T10:00:00+00:00",
        "  end: 2026-06-17T11:00:00+00:00",
        "  location: Room A",
        "  source_id: lark-1",
    ]
    assert "secret" not in "\n".join(messages)


def test_list_lark_events_formats_empty_location(monkeypatch):
    class NoLocationComponent(FakeComponent):
        def __init__(self):
            super().__init__()
            del self.location

    class NoLocationVobject:
        def components(self):
            return [NoLocationComponent()]

    class NoLocationResult(FakeResult):
        vobject_instance = NoLocationVobject()

    class NoLocationCalendar(FakeCalendar):
        def get_objects_by_sync_token(
            self,
            *,
            sync_token=None,
            load_objects=False,
            disable_fallback=False,
        ):
            return FakeSyncCollection([NoLocationResult()])

    class NoLocationClient(FakeClient):
        def calendar(self, *, url):
            return NoLocationCalendar()

    messages: list[str] = []
    config = CaldavConfig(
        host="https://caldav.example.com",
        username="alice",
        password="secret",
        calendar_url="https://caldav.example.com/calendars/alice/work",
    )

    monkeypatch.setattr("cal_sync.lark_caldav.DAVClient", NoLocationClient)

    list_lark_events(
        config,
        datetime(2026, 6, 17, 10, 0, tzinfo=UTC),
        datetime(2026, 6, 17, 11, 0, tzinfo=UTC),
        progress=messages.append,
        verbose=True,
    )

    assert "  location: <empty>" in messages


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
    assert "No CalDAV object resources were returned by sync-token object loading." in dump


def test_list_lark_events_uses_saved_sync_token_and_cache(monkeypatch, tmp_path):
    class UpdatedComponent(FakeComponent):
        def __init__(self):
            super().__init__()
            self.uid = FakeText("lark-2")
            self.summary = FakeText("Updated")
            self.dtstart = FakeText(datetime(2026, 6, 17, 12, 0, tzinfo=UTC))
            self.dtend = FakeText(datetime(2026, 6, 17, 13, 0, tzinfo=UTC))

    class UpdatedVobject:
        def components(self):
            return [UpdatedComponent()]

    class UpdatedResult(FakeResult):
        url = "https://caldav.example.com/calendars/alice/work/lark-2.ics"
        vobject_instance = UpdatedVobject()

    state_path = tmp_path / "lark-state.json"
    state_path.write_text(
        json.dumps(
            {
                "sync_token": "sync-token-old",
                "events_by_url": {
                    "https://caldav.example.com/calendars/alice/work/lark-1.ics": {
                        "source_id": "lark-1",
                        "summary": "Planning",
                        "description": "Discuss roadmap",
                        "location": "Room A",
                        "start": "2026-06-17T10:00:00+00:00",
                        "end": "2026-06-17T11:00:00+00:00",
                        "updated_at": None,
                        "etag": "etag-1",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    class IncrementalCalendar:
        url = "https://caldav.example.com/calendars/alice/work"

        def __init__(self):
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
            return FakeSyncCollection([UpdatedResult()], sync_token="sync-token-new")

        def search(self, **kwargs):
            raise AssertionError("search should not be called")

    calendar = IncrementalCalendar()

    class IncrementalClient(FakeClient):
        def calendar(self, *, url):
            return calendar

    config = CaldavConfig(
        host="https://caldav.example.com",
        username="alice",
        password="secret",
        calendar_url="https://caldav.example.com/calendars/alice/work",
        state_path=state_path,
    )
    start = datetime(2026, 6, 17, 10, 0, tzinfo=UTC)
    end = datetime(2026, 6, 17, 14, 0, tzinfo=UTC)

    monkeypatch.setattr("cal_sync.lark_caldav.DAVClient", IncrementalClient)

    events = list_lark_events(
        config,
        start,
        end,
    )

    assert [event.source_id for event in events] == ["lark-1", "lark-2"]
    assert calendar.sync_kwargs == {
        "sync_token": "sync-token-old",
        "load_objects": True,
        "disable_fallback": True,
    }
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["sync_token"] == "sync-token-new"
    assert sorted(event["source_id"] for event in saved["events_by_url"].values()) == [
        "lark-1",
        "lark-2",
    ]


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
    )

    assert [event.source_id for event in events] == ["lark-1"]
    assert calendar.sync_kwargs == {
        "sync_token": None,
        "load_objects": True,
        "disable_fallback": True,
    }
    assert calendar.search_called is False


def test_list_lark_events_skips_sync_loaded_objects_without_vobject(monkeypatch, tmp_path):
    class EmptyResult(FakeResult):
        url = "https://caldav.example.com/calendars/alice/work/empty.ics"
        data = None
        vobject_instance = None

    class SyncCalendar:
        url = "https://caldav.example.com/calendars/alice/work"

        def get_objects_by_sync_token(
            self,
            *,
            sync_token=None,
            load_objects=False,
            disable_fallback=False,
        ):
            return [EmptyResult(), FakeResult()]

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
    messages: list[str] = []
    dump_path = tmp_path / "lark-response.txt"

    monkeypatch.setattr("cal_sync.lark_caldav.DAVClient", SyncClient)

    events = list_lark_events(
        config,
        datetime(2026, 6, 17, 9, 0, tzinfo=UTC),
        datetime(2026, 6, 17, 12, 0, tzinfo=UTC),
        progress=messages.append,
        verbose=True,
        dump_response_path=dump_path,
    )

    assert [event.source_id for event in events] == ["lark-1"]
    assert (
        "Skipped Lark CalDAV object: reason=missing vobject_instance "
        "identity=url=https://caldav.example.com/calendars/alice/work/empty.ics"
    ) in messages
    dump = dump_path.read_text(encoding="utf-8")
    assert "url: https://caldav.example.com/calendars/alice/work/empty.ics" in dump
    assert "#### vobject_instance" in dump
    assert "<missing>" in dump


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
        url = "https://caldav.example.com/calendars/alice/work/outside-window.ics"
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
    messages: list[str] = []

    monkeypatch.setattr("cal_sync.lark_caldav.DAVClient", SyncClient)

    events = list_lark_events(
        config,
        datetime(2026, 6, 17, 9, 0, tzinfo=UTC),
        datetime(2026, 6, 17, 12, 0, tzinfo=UTC),
        progress=messages.append,
        verbose=True,
    )

    assert [event.source_id for event in events] == ["lark-1"]
    assert "Skipped cached Lark events outside sync window: 1" in messages
    assert not any("reason=outside sync window" in message for message in messages)
