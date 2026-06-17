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

The file contains CalDAV credentials, the Lark sync state path, Google OAuth
paths, sync date range, and log path. It must not be committed to Git.

## Google setup

The init wizard asks for two Google values.

### Google Calendar ID

Use `primary` when syncing to your default Google Calendar.

For a non-default calendar:

1. Open [Google Calendar](https://calendar.google.com/).
2. In the left sidebar, find the calendar.
3. Open the calendar menu and choose `Settings and sharing`.
4. Find `Integrate calendar`.
5. Copy `Calendar ID`.

Personal calendar IDs often look like an email address. Shared calendar IDs can
look like `example.com_abc123@group.calendar.google.com`.

### Google OAuth client JSON path

This is the local path to a downloaded Google OAuth desktop client JSON file.

To create it:

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a project.
3. Enable `Google Calendar API` for the project.
4. Open `APIs & Services` -> `OAuth consent screen` and finish the required
   setup.
5. Open `APIs & Services` -> `Credentials`.
6. Choose `Create credentials` -> `OAuth client ID`.
7. Select `Desktop app` as the application type.
8. Download the JSON file.
9. Store it outside the repository, for example:

```text
${XDG_CONFIG_HOME:-~/.config}/lark-google-calendar-sync/google.credentials.json
```

When the wizard asks for `Google OAuth client JSON path`, enter the full local
path to that downloaded JSON file.

On a system without a runnable browser, choose to authorize when prompted. The
tool prints a Google authorization URL. Open that URL in a browser on another
machine, finish Google authorization, then copy the full final URL that starts
with `http://localhost` back into the terminal prompt. The localhost page may
fail to load on that browser machine, which is expected; copy the URL from the
address bar.

## Usage

Create a Google OAuth desktop client JSON file in Google Cloud Console, then run:

```bash
uv run lark-gcal init
```

The wizard asks for:

- Lark CalDAV host, username, and password.
- The Lark calendar to read from.
- Lark sync state path.
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

Lark event loading uses CalDAV sync-token object loading. The first run for a
new state file performs an initial collection sync. Later runs reuse the saved
sync token and local event cache, so they only need CalDAV changes from Feishu
and then filter the configured date window locally. The date-range CalDAV search
path is intentionally not used because Feishu returns empty results for it in
this environment.
