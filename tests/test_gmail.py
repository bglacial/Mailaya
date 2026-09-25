from dataclasses import replace
from urllib.parse import parse_qs, urlparse

from app.config import get_settings
from app.gmail import GMAIL_SCOPE, GmailMailClient, GoogleAuth


def test_gmail_message_is_normalized_for_the_shared_pipeline():
    message = {
        "id": "gmail-123",
        "internalDate": "1789992000000",
        "snippet": "Merci de confirmer &amp; répondre.",
        "payload": {
            "headers": [
                {"name": "From", "value": "Camille Martin <camille@example.com>"},
                {"name": "Subject", "value": "Validation attendue"},
            ]
        },
    }

    result = GmailMailClient.message_to_email(message)

    assert result["graph_id"] == "gmail-123"
    assert result["sender_name"] == "Camille Martin"
    assert result["sender_address"] == "camille@example.com"
    assert result["subject"] == "Validation attendue"
    assert result["body_preview"] == "Merci de confirmer & répondre."
    assert result["received_at"].endswith("+00:00")


def test_google_auth_builds_a_read_only_consent_url(tmp_path):
    settings = replace(
        get_settings(),
        google_client_id="client-id.apps.googleusercontent.com",
        google_client_secret="client-secret",
        google_token_path=tmp_path / "google-token.json",
    )
    auth = GoogleAuth(settings)

    authorization_url = auth.start_flow("http://127.0.0.1:8000/api/auth/google/callback")
    query = parse_qs(urlparse(authorization_url).query)

    assert query["client_id"] == ["client-id.apps.googleusercontent.com"]
    assert query["redirect_uri"] == ["http://127.0.0.1:8000/api/auth/google/callback"]
    assert query["scope"] == [GMAIL_SCOPE]
    assert query["access_type"] == ["offline"]
    assert query["state"][0]


def test_dashboard_shows_the_redirect_uri_for_its_current_origin(monkeypatch, tmp_path):
    monkeypatch.setenv("LAYA_BACKEND", "demo")
    monkeypatch.setenv("LAYA_MAIL_DATA_DIR", str(tmp_path))

    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app, base_url="http://127.0.0.1:8766")
    configuration = client.get("/api/dashboard").json()["configuration"]

    assert configuration["gmail_redirect_uri"] == "http://127.0.0.1:8766/api/auth/google/callback"
    assert set(client.get("/api/dashboard").json()["auth"]) == {"gmail"}
    assert client.post(
        "/api/runs", json={"source": "outlook", "since_date": "2026-09-01", "limit": 1}
    ).status_code == 422
    assert client.post("/api/auth/device-code").status_code == 404


def test_gmail_decodes_internationalized_headers():
    message = {
        "id": "gmail-encoded",
        "internalDate": "1789992000000",
        "snippet": "Bonjour",
        "payload": {
            "headers": [
                {"name": "From", "value": "=?UTF-8?Q?Andr=C3=A9?= <andre@example.com>"},
                {"name": "Subject", "value": "=?UTF-8?Q?R=C3=A9union_=C3=A0_14_h?="},
            ]
        },
    }

    result = GmailMailClient.message_to_email(message)

    assert result["sender_name"] == "André"
    assert result["subject"] == "Réunion à 14 h"
