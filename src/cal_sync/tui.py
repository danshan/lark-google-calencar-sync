from __future__ import annotations

from pathlib import Path

from rich.prompt import Confirm, IntPrompt, Prompt

from cal_sync.config import AppConfig, CaldavConfig, GoogleConfig, SyncConfig
from cal_sync.google_calendar import load_credentials
from cal_sync.lark_caldav import list_lark_calendars


def run_init_wizard(config_path: Path | None = None) -> AppConfig:
    target_path = config_path or AppConfig.default_path()
    existing = AppConfig.load(target_path) if target_path.exists() else AppConfig()
    print(f"Writing config to {target_path}")

    caldav = CaldavConfig(
        host=Prompt.ask("Lark CalDAV host", default=existing.caldav.host),
        username=Prompt.ask("Lark CalDAV username", default=existing.caldav.username),
        password=Prompt.ask(
            "Lark CalDAV password",
            default=existing.caldav.password,
            password=True,
        ),
    )

    calendars = list_lark_calendars(caldav)
    for index, (name, url) in enumerate(calendars, start=1):
        print(f"{index}. {name} - {url}")
    selected = IntPrompt.ask(
        "Select Lark calendar",
        default=_calendar_default_index(calendars, existing.caldav.calendar_url),
    )
    caldav.calendar_url = calendars[selected - 1][1]

    google = GoogleConfig(
        calendar_id=Prompt.ask("Google Calendar ID", default=existing.google.calendar_id),
        credentials_path=Path(
            Prompt.ask(
                "Google OAuth client JSON path",
                default=str(existing.google.credentials_path),
            )
        ),
        token_path=existing.google.token_path
        if existing.google.token_path != GoogleConfig().token_path
        else target_path.parent / "google.token.json",
    )

    sync = SyncConfig(
        past_days=IntPrompt.ask("Sync past days", default=existing.sync.past_days),
        future_days=IntPrompt.ask("Sync future days", default=existing.sync.future_days),
        dry_run=Confirm.ask("Enable dry run by default?", default=existing.sync.dry_run),
    )
    log_default = (
        existing.log_path
        if existing.log_path != AppConfig().log_path
        else target_path.parent / "sync.log"
    )
    log_path = Path(Prompt.ask("Sync log path", default=str(log_default))).expanduser()

    config = AppConfig(caldav=caldav, google=google, sync=sync, log_path=log_path)
    config.save(target_path)

    if Confirm.ask("Open browser to authorize Google now?", default=True):
        load_credentials(config.google.credentials_path, config.google.token_path)

    return config


def _calendar_default_index(calendars: list[tuple[str, str]], calendar_url: str) -> int:
    for index, (_, url) in enumerate(calendars, start=1):
        if url == calendar_url:
            return index
    return 1
