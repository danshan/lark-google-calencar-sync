from __future__ import annotations

from pathlib import Path

from rich.prompt import Confirm, IntPrompt, Prompt

from cal_sync.config import AppConfig, CaldavConfig, GoogleConfig, SyncConfig
from cal_sync.google_calendar import load_credentials
from cal_sync.lark_caldav import list_lark_calendars


def run_init_wizard(config_path: Path | None = None) -> AppConfig:
    target_path = config_path or AppConfig.default_path()
    print(f"Writing config to {target_path}")

    caldav = CaldavConfig(
        host=Prompt.ask("Lark CalDAV host"),
        username=Prompt.ask("Lark CalDAV username"),
        password=Prompt.ask("Lark CalDAV password", password=True),
    )

    calendars = list_lark_calendars(caldav)
    for index, (name, url) in enumerate(calendars, start=1):
        print(f"{index}. {name} - {url}")
    selected = IntPrompt.ask("Select Lark calendar", default=1)
    caldav.calendar_url = calendars[selected - 1][1]

    google = GoogleConfig(
        calendar_id=Prompt.ask("Google Calendar ID", default="primary"),
        credentials_path=Path(Prompt.ask("Google OAuth client JSON path")),
        token_path=target_path.parent / "google.token.json",
    )

    sync = SyncConfig(
        past_days=IntPrompt.ask("Sync past days", default=7),
        future_days=IntPrompt.ask("Sync future days", default=30),
        dry_run=Confirm.ask("Enable dry run by default?", default=False),
    )
    log_path = Path(
        Prompt.ask("Sync log path", default=str(target_path.parent / "sync.log"))
    ).expanduser()

    config = AppConfig(caldav=caldav, google=google, sync=sync, log_path=log_path)
    config.save(target_path)

    if Confirm.ask("Open browser to authorize Google now?", default=True):
        load_credentials(config.google.credentials_path, config.google.token_path)

    return config

