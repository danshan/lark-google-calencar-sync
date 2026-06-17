from pathlib import Path

from typer.testing import CliRunner

from cal_sync.cli import app
from cal_sync.config import AppConfig, CaldavConfig, GoogleConfig
from cal_sync.google_calendar import GoogleAuthorizationError
from cal_sync.lark_caldav import LarkCaldavAuthenticationError


def test_lark_calendars_lists_configured_caldav_calendars(monkeypatch, tmp_path):
    config_path = tmp_path / "config.toml"
    AppConfig(
        caldav=CaldavConfig(
            host="https://caldav.example.com",
            username="alice",
            password="secret",
        ),
        google=GoogleConfig(
            credentials_path=Path("google.credentials.json"),
            token_path=Path("google.token.json"),
        ),
    ).save(config_path)
    monkeypatch.setattr(
        "cal_sync.cli.list_lark_calendars",
        lambda config: [
            ("Default", "https://caldav.example.com/calendars/alice/default"),
            ("Work", "https://caldav.example.com/calendars/alice/work"),
        ],
    )

    result = CliRunner().invoke(app, ["lark-calendars", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "1. Default - https://caldav.example.com/calendars/alice/default" in result.output
    assert "2. Work - https://caldav.example.com/calendars/alice/work" in result.output
    assert "secret" not in result.output


def test_lark_calendars_reports_auth_error_without_traceback(monkeypatch, tmp_path):
    config_path = tmp_path / "config.toml"
    AppConfig(
        caldav=CaldavConfig(
            host="https://caldav.example.com",
            username="alice",
            password="secret",
        ),
        google=GoogleConfig(
            credentials_path=Path("google.credentials.json"),
            token_path=Path("google.token.json"),
        ),
    ).save(config_path)

    def list_lark_calendars(config):
        raise LarkCaldavAuthenticationError(
            "Lark CalDAV authorization failed. Check host, username, and password."
        )

    monkeypatch.setattr("cal_sync.cli.list_lark_calendars", list_lark_calendars)

    result = CliRunner().invoke(app, ["lark-calendars", "--config", str(config_path)])

    assert result.exit_code == 1
    assert "Lark CalDAV authorization failed" in result.output
    assert "Traceback" not in result.output
    assert "secret" not in result.output


def test_init_reports_auth_error_without_traceback(monkeypatch):
    def run_init_wizard(config):
        raise LarkCaldavAuthenticationError(
            "Lark CalDAV authorization failed. Check host, username, and password."
        )

    monkeypatch.setattr("cal_sync.cli.run_init_wizard", run_init_wizard)

    result = CliRunner().invoke(app, ["init"])

    assert result.exit_code == 1
    assert "Lark CalDAV authorization failed" in result.output
    assert "Traceback" not in result.output


def test_init_reports_google_auth_error_without_traceback(monkeypatch):
    def run_init_wizard(config):
        raise GoogleAuthorizationError(
            "Google authorization requires a browser or a pasted redirected URL."
        )

    monkeypatch.setattr("cal_sync.cli.run_init_wizard", run_init_wizard)

    result = CliRunner().invoke(app, ["init"])

    assert result.exit_code == 1
    assert "Google authorization requires a browser" in result.output
    assert "Traceback" not in result.output
