from datetime import UTC, datetime
from pathlib import Path

from cal_sync.config import AppConfig, CaldavConfig, GoogleConfig, SyncConfig
from cal_sync.models import CalendarEvent
from cal_sync.runtime import sync_once


def test_sync_once_reports_progress_and_writes_log(monkeypatch, tmp_path):
    event = CalendarEvent(
        source_id="lark-1",
        summary="Planning",
        start=datetime(2026, 6, 17, 10, 0, tzinfo=UTC),
        end=datetime(2026, 6, 17, 11, 0, tzinfo=UTC),
    )
    config = AppConfig(
        caldav=CaldavConfig(host="https://caldav.example.com", username="alice", password="secret"),
        google=GoogleConfig(
            calendar_id="primary",
            credentials_path=Path("google.credentials.json"),
            token_path=Path("google.token.json"),
        ),
        sync=SyncConfig(dry_run=True),
        log_path=tmp_path / "sync.log",
    )
    progress_messages: list[str] = []

    monkeypatch.setattr(
        "cal_sync.runtime.sync_window",
        lambda past, future: (event.start, event.end),
    )
    monkeypatch.setattr(
        "cal_sync.runtime.list_lark_events",
        lambda caldav, start, end, *, progress=None, verbose=False, dump_response_path=None: [
            event
        ],
    )
    monkeypatch.setattr("cal_sync.runtime.build_google_service", lambda google: object())
    monkeypatch.setattr(
        "cal_sync.runtime.list_google_events",
        lambda service, calendar_id, start, end: [],
    )

    plan = sync_once(config, progress=progress_messages.append)

    assert [item.source_id for item in plan.to_create] == ["lark-1"]
    assert progress_messages == [
        "Sync window: 2026-06-17T10:00:00+00:00 -> 2026-06-17T11:00:00+00:00",
        "Loading Lark CalDAV events...",
        "Loaded 1 Lark events.",
        "Authorizing Google Calendar...",
        "Loading Google Calendar events...",
        "Loaded 0 Google events.",
        "Plan: create=1 update=0 delete=0 dry_run=True",
        "Dry run enabled. Google Calendar was not modified.",
    ]
    log_text = config.log_path.read_text(encoding="utf-8")
    assert "Sync started" in log_text
    assert "Loaded Lark events: count=1" in log_text
    assert "Dry run enabled" in log_text


def test_sync_once_passes_verbose_to_lark_loader(monkeypatch, tmp_path):
    config = AppConfig(
        caldav=CaldavConfig(host="https://caldav.example.com", username="alice", password="secret"),
        google=GoogleConfig(
            calendar_id="primary",
            credentials_path=Path("google.credentials.json"),
            token_path=Path("google.token.json"),
        ),
        sync=SyncConfig(dry_run=True),
        log_path=tmp_path / "sync.log",
    )
    dump_path = tmp_path / "lark-response.txt"
    seen: dict[str, object] = {}

    def list_lark_events(
        caldav,
        start,
        end,
        *,
        progress=None,
        verbose=False,
        dump_response_path=None,
    ):
        seen["verbose"] = verbose
        seen["dump_response_path"] = dump_response_path
        return []

    monkeypatch.setattr(
        "cal_sync.runtime.sync_window",
        lambda past, future: (
            datetime(2026, 6, 17, 10, 0, tzinfo=UTC),
            datetime(2026, 6, 17, 11, 0, tzinfo=UTC),
        ),
    )
    monkeypatch.setattr("cal_sync.runtime.list_lark_events", list_lark_events)
    monkeypatch.setattr("cal_sync.runtime.build_google_service", lambda google: object())
    monkeypatch.setattr(
        "cal_sync.runtime.list_google_events",
        lambda service, calendar_id, start, end: [],
    )

    sync_once(
        config,
        progress=lambda message: None,
        verbose=True,
        dump_lark_response_path=dump_path,
    )

    assert seen == {"verbose": True, "dump_response_path": dump_path}
