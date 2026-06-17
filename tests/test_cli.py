from pathlib import Path

from typer.testing import CliRunner

from cal_sync.cli import app
from cal_sync.config import AppConfig, CaldavConfig, GoogleConfig


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
