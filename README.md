# Lark Google Calendar Sync

A local Python CLI/TUI utility for one-way synchronization from a Lark CalDAV
calendar to Google Calendar.

## Development

```bash
uv sync
uv run pytest
uv run lark-gcal --help
```

## Local configuration

Runtime configuration is stored outside the repository by default:

```text
${XDG_CONFIG_HOME:-~/.config}/lark-google-calendar-sync/config.toml
```

The file contains CalDAV credentials, Google OAuth paths, sync date range, and
log path. It must not be committed to Git.

## Usage

Create a Google OAuth desktop client JSON file in Google Cloud Console, then run:

```bash
uv run lark-gcal init
```

The wizard asks for:

- Lark CalDAV host, username, and password.
- The Lark calendar to read from.
- Google Calendar ID, usually `primary`.
- Google OAuth client JSON path.
- Sync date window, such as past 7 days and future 30 days.
- Log file path.

The wizard can open a browser to complete Google OAuth and stores the token next
to the local config file.

Run a dry sync:

```bash
uv run lark-gcal sync --dry-run
```

Apply changes to Google Calendar:

```bash
uv run lark-gcal sync --apply
```

The sync is one-way from Lark to Google. Google events created by this tool are
marked with a private `larkSourceId` extended property. Sync deletes only those
managed Google events when the matching Lark event disappears, and leaves
personal or unrelated Google events untouched.
