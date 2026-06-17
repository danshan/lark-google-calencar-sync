# AGENTS.md

## Project Scope

This repository contains a local Python tool that synchronizes events from a
Lark CalDAV calendar to Google Calendar.

The sync direction is one-way:

- Source of truth: Lark CalDAV.
- Target: Google Calendar.
- Google events are created, patched, or deleted only when they are managed by
  this tool.

Managed Google events are identified by the private extended property
`larkSourceId`. Do not delete or modify unrelated Google events.

## Tech Stack

- Python 3.12+.
- `uv` for dependency and virtualenv management.
- Typer CLI with Rich prompts for local initialization.
- `caldav` for Lark CalDAV access.
- `google-api-python-client` and `google-auth-oauthlib` for Google Calendar
  CRUD and OAuth.
- Pydantic models for config and event data.

## Commands

Install dependencies:

```bash
uv sync
```

Run tests:

```bash
uv run pytest
```

Run lint:

```bash
uv run ruff check .
```

Show CLI help:

```bash
uv run lark-gcal --help
```

Initialize local config:

```bash
uv run lark-gcal init
```

Preview sync changes:

```bash
uv run lark-gcal sync --dry-run
```

Apply sync changes:

```bash
uv run lark-gcal sync --apply
```

## Local State And Git Hygiene

The runtime config is local-only and must not be committed:

```text
${XDG_CONFIG_HOME:-~/.config}/lark-google-calendar-sync/config.toml
```

Do not commit:

- CalDAV passwords.
- Google OAuth client secrets.
- Google OAuth tokens.
- Sync logs.
- `.venv` or cache directories.

Keep `.gitignore` aligned with those rules.

## Code Organization

- `src/cal_sync/config.py`: local config model and TOML persistence.
- `src/cal_sync/models.py`: internal event model.
- `src/cal_sync/sync.py`: pure diff logic for create, update, delete plans.
- `src/cal_sync/lark_caldav.py`: CalDAV reads and iCalendar parsing.
- `src/cal_sync/google_calendar.py`: Google Calendar OAuth, event mapping, and
  CRUD.
- `src/cal_sync/runtime.py`: sync orchestration and logging.
- `src/cal_sync/cli.py`: command entry points.
- `src/cal_sync/tui.py`: interactive initialization wizard.

Keep sync policy in `sync.py` testable without network access. External API
code should stay in adapter modules.

## Development Rules

- Add or update tests for non-trivial sync behavior before changing production
  logic.
- Prefer small, reviewable changes.
- Do not introduce background deletion behavior without a test proving unrelated
  Google events are preserved.
- Do not put Chinese text in code, comments, commit messages, or command output
  fixtures.
- Run `uv run pytest` and `uv run ruff check .` before claiming completion.
