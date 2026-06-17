from pathlib import Path

from cal_sync.config import AppConfig, CaldavConfig, GoogleConfig, SyncConfig


def test_default_config_path_uses_local_user_config_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert AppConfig.default_path() == tmp_path / "lark-google-calendar-sync" / "config.toml"


def test_config_round_trip_persists_expected_sections(tmp_path):
    config_path = tmp_path / "config.toml"
    config = AppConfig(
        caldav=CaldavConfig(
            host="https://caldav.example.com",
            username="alice",
            password="secret",
            calendar_url="https://caldav.example.com/calendars/alice/work",
            state_path=Path("lark-state.json"),
        ),
        google=GoogleConfig(
            calendar_id="primary",
            credentials_path=Path("client_secret.json"),
            token_path=Path("token.json"),
        ),
        sync=SyncConfig(past_days=14, future_days=45),
        log_path=Path("sync.log"),
    )

    config.save(config_path)
    loaded = AppConfig.load(config_path)

    assert loaded.caldav.host == "https://caldav.example.com"
    assert loaded.caldav.username == "alice"
    assert loaded.caldav.password == "secret"
    assert loaded.caldav.calendar_url == "https://caldav.example.com/calendars/alice/work"
    assert loaded.caldav.state_path == Path("lark-state.json")
    assert loaded.google.calendar_id == "primary"
    assert loaded.sync.past_days == 14
    assert loaded.sync.future_days == 45
    assert loaded.log_path == Path("sync.log")
