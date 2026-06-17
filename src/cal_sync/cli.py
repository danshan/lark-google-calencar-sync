from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from cal_sync.config import AppConfig
from cal_sync.lark_caldav import list_lark_calendars
from cal_sync.runtime import sync_once
from cal_sync.tui import run_init_wizard

app = typer.Typer(no_args_is_help=True)


@app.command("config-path")
def config_path() -> None:
    typer.echo(AppConfig.default_path())


@app.command("lark-calendars")
def lark_calendars(
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to local config file."),
    ] = None,
) -> None:
    app_config = AppConfig.load(config)
    typer.echo(f"Lark CalDAV host: {app_config.caldav.host}")
    typer.echo(f"Lark CalDAV username: {app_config.caldav.username}")
    calendars = list_lark_calendars(app_config.caldav)
    if not calendars:
        typer.echo("No Lark calendars returned by CalDAV principal.")
        return

    for index, (name, url) in enumerate(calendars, start=1):
        typer.echo(f"{index}. {name} - {url}")


@app.command("init")
def init(
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to local config file."),
    ] = None,
) -> None:
    written = run_init_wizard(config)
    typer.echo(f"Config saved to {config or written.default_path()}")


@app.command("sync")
def sync(
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to local config file."),
    ] = None,
    dry_run: Annotated[
        bool | None,
        typer.Option("--dry-run/--apply", help="Override config dry-run flag."),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Print detailed diagnostics while syncing."),
    ] = False,
    dump_lark_response: Annotated[
        Path | None,
        typer.Option(
            "--dump-lark-response",
            help="Write raw Lark CalDAV search results to a local diagnostic file.",
        ),
    ] = None,
    lark_sync_token: Annotated[
        bool,
        typer.Option(
            "--lark-sync-token",
            help="Try CalDAV sync-collection before search. May hang on some servers.",
        ),
    ] = False,
) -> None:
    app_config = AppConfig.load(config)
    if dry_run is not None:
        app_config.sync.dry_run = dry_run

    typer.echo(f"Writing sync log to {app_config.log_path}")
    plan = sync_once(
        app_config,
        progress=typer.echo,
        verbose=verbose,
        dump_lark_response_path=dump_lark_response,
        use_lark_sync_token=lark_sync_token,
    )
    typer.echo(
        f"create={len(plan.to_create)} update={len(plan.to_update)} "
        f"delete={len(plan.to_delete)} dry_run={app_config.sync.dry_run}"
    )
