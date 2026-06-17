from datetime import UTC, datetime

from cal_sync.google_calendar import (
    GOOGLE_SOURCE_KEY,
    event_to_google_body,
    google_item_to_event,
    load_credentials,
)
from cal_sync.models import CalendarEvent


def test_event_to_google_body_marks_lark_source_id():
    event = CalendarEvent(
        source_id="lark-123",
        summary="Focus",
        description="Deep work",
        location="Home",
        start=datetime(2026, 6, 17, 10, 0, tzinfo=UTC),
        end=datetime(2026, 6, 17, 11, 0, tzinfo=UTC),
    )

    body = event_to_google_body(event)

    assert body["summary"] == "Focus"
    assert body["extendedProperties"]["private"][GOOGLE_SOURCE_KEY] == "lark-123"
    assert body["start"]["dateTime"] == "2026-06-17T10:00:00+00:00"
    assert body["end"]["dateTime"] == "2026-06-17T11:00:00+00:00"


def test_google_item_to_event_returns_external_without_source_marker():
    item = {
        "id": "google-1",
        "summary": "Personal",
        "start": {"dateTime": "2026-06-17T10:00:00+00:00"},
        "end": {"dateTime": "2026-06-17T11:00:00+00:00"},
    }

    event = google_item_to_event(item)

    assert event.source_id == "external"
    assert event.google_id == "google-1"


def test_load_credentials_falls_back_to_manual_oauth_when_browser_is_missing(
    monkeypatch,
    tmp_path,
    capsys,
):
    import webbrowser

    class FakeCredentials:
        valid = True
        expired = False
        refresh_token = None

        def to_json(self):
            return '{"token": "fake"}'

    class FakeFlow:
        credentials = FakeCredentials()

        def __init__(self):
            self.redirect_uri = None
            self.authorization_response = None

        def run_local_server(self, *, port):
            raise webbrowser.Error("could not locate runnable browser")

        def authorization_url(self, **kwargs):
            return "https://accounts.example.com/auth", "state"

        def fetch_token(self, **kwargs):
            self.authorization_response = kwargs["authorization_response"]

    flow = FakeFlow()

    monkeypatch.setattr(
        "cal_sync.google_calendar.InstalledAppFlow.from_client_secrets_file",
        lambda path, scopes: flow,
    )
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt: "http://localhost/?state=state&code=auth-code&scope=calendar",
    )

    token_path = tmp_path / "google.token.json"
    credentials = load_credentials(tmp_path / "google.credentials.json", token_path)

    assert credentials is flow.credentials
    assert flow.redirect_uri == "http://localhost"
    assert flow.authorization_response == "http://localhost/?state=state&code=auth-code&scope=calendar"
    assert token_path.read_text(encoding="utf-8") == '{"token": "fake"}'
    output = capsys.readouterr().out
    assert "No runnable browser was found" in output
    assert "https://accounts.example.com/auth" in output
