from pathlib import Path

from cal_sync.config import AppConfig, CaldavConfig, GoogleConfig, SyncConfig
from cal_sync.tui import run_init_wizard


def test_init_wizard_prefills_existing_config(monkeypatch, tmp_path):
    config_path = tmp_path / "config.toml"
    existing = AppConfig(
        caldav=CaldavConfig(
            host="https://caldav.example.com",
            username="alice",
            password="secret",
            calendar_url="https://caldav.example.com/calendars/alice/work",
        ),
        google=GoogleConfig(
            calendar_id="work-calendar",
            credentials_path=Path("/secrets/google.credentials.json"),
            token_path=Path("/secrets/google.token.json"),
        ),
        sync=SyncConfig(past_days=14, future_days=45, dry_run=True),
        log_path=Path("/tmp/sync.log"),
    )
    existing.save(config_path)

    prompt_defaults: dict[str, object] = {}
    int_defaults: dict[str, object] = {}
    confirm_defaults: dict[str, object] = {}

    def prompt_ask(label, *, default=None, password=False):
        prompt_defaults[label] = default
        return default

    def int_ask(label, *, default=None):
        int_defaults[label] = default
        return default

    def confirm_ask(label, *, default=None):
        confirm_defaults[label] = default
        return False if label == "Open browser to authorize Google now?" else default

    monkeypatch.setattr("cal_sync.tui.Prompt.ask", prompt_ask)
    monkeypatch.setattr("cal_sync.tui.IntPrompt.ask", int_ask)
    monkeypatch.setattr("cal_sync.tui.Confirm.ask", confirm_ask)
    monkeypatch.setattr(
        "cal_sync.tui.list_lark_calendars",
        lambda config: [("Work", "https://caldav.example.com/calendars/alice/work")],
    )

    config = run_init_wizard(config_path)

    assert prompt_defaults["Lark CalDAV host"] == "https://caldav.example.com"
    assert prompt_defaults["Lark CalDAV username"] == "alice"
    assert prompt_defaults["Lark CalDAV password"] == "secret"
    assert prompt_defaults["Google Calendar ID"] == "work-calendar"
    assert prompt_defaults["Google OAuth client JSON path"] == "/secrets/google.credentials.json"
    assert int_defaults["Sync past days"] == 14
    assert int_defaults["Sync future days"] == 45
    assert confirm_defaults["Enable dry run by default?"] is True
    assert config == existing
