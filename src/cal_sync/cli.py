from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from cal_sync.config import AppConfig
from cal_sync.runtime import sync_once
from cal_sync.tui import run_init_wizard

app = typer.Typer(no_args_is_help=True)


@app.command("config-path")
def config_path() -> None:
    typer.echo(AppConfig.default_path())


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
) -> None:
    app_config = AppConfig.load(config)
    if dry_run is not None:
        app_config.sync.dry_run = dry_run

    typer.echo(f"Writing sync log to {app_config.log_path}")
    plan = sync_once(app_config, progress=typer.echo)
    typer.echo(
        f"create={len(plan.to_create)} update={len(plan.to_update)} "
        f"delete={len(plan.to_delete)} dry_run={app_config.sync.dry_run}"
    )
