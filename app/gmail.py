from __future__ import annotations

import html
import secrets
import threading
from datetime import date, datetime, time, timezone
from email.header import decode_header, make_header
from email.utils import parseaddr
from typing import Any

import httpx

from .config import Settings


GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_MESSAGES_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"


def _decode_mail_header(value: str) -> str:
    try:
        return str(make_header(decode_header(value)))
    except (LookupError, UnicodeError):
        return value


class GoogleAuth:
    """OAuth web flow for a single-user local application."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.RLock()
        self._flows: dict[str, Any] = {}
        self._last_error: str | None = None

    def _client_config(self, redirect_uri: str) -> dict[str, Any]:
        if not self.settings.gmail_configured:
            raise RuntimeError("GOOGLE_CLIENT_ID et GOOGLE_CLIENT_SECRET ne sont pas configurés.")
        return {
            "web": {
                "client_id": self.settings.google_client_id,
                "client_secret": self.settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        }

    def _load_credentials(self) -> Any | None:
        path = self.settings.google_token_path
        if not path.exists():
            return None
        try:
            from google.oauth2.credentials import Credentials

            return Credentials.from_authorized_user_file(path, [GMAIL_SCOPE])
        except (ImportError, ValueError) as exc:
            self._last_error = f"Le jeton Google local est illisible : {exc}"
            return None

    def _save_credentials(self, credentials: Any) -> None:
        path = self.settings.google_token_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(credentials.to_json(), encoding="utf-8")
        path.chmod(0o600)

    def status(self) -> dict[str, Any]:
        if not self.settings.gmail_configured:
            return {"state": "unconfigured", "configured": False, "error": None}
        with self._lock:
            credentials = self._load_credentials()
            if credentials and credentials.valid:
                return {"state": "connected", "configured": True, "error": None}
            if credentials and credentials.refresh_token:
                try:
                    self._refresh(credentials)
                    return {"state": "connected", "configured": True, "error": None}
                except RuntimeError as exc:
                    self._last_error = str(exc)
            return {"state": "disconnected", "configured": True, "error": self._last_error}

    def start_flow(self, redirect_uri: str) -> str:
        try:
            from google_auth_oauthlib.flow import Flow
        except ImportError as exc:
            raise RuntimeError("Le paquet google-auth-oauthlib n'est pas installé.") from exc

        state = secrets.token_urlsafe(32)
        flow = Flow.from_client_config(
            self._client_config(redirect_uri), scopes=[GMAIL_SCOPE], state=state
        )
        flow.redirect_uri = redirect_uri
        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        with self._lock:
            self._flows[state] = flow
            self._last_error = None
        return authorization_url

    def finish_flow(self, state: str, code: str) -> None:
        with self._lock:
            flow = self._flows.pop(state, None)
        if flow is None:
            raise RuntimeError("La demande de connexion Google a expiré. Recommencez depuis l'application.")
        try:
            flow.fetch_token(code=code)
            self._save_credentials(flow.credentials)
            self._last_error = None
        except Exception as exc:
            self._last_error = str(exc)
            raise RuntimeError("Google n'a pas pu terminer la connexion.") from exc

    def _refresh(self, credentials: Any) -> None:
        try:
            from google.auth.transport.requests import Request

            credentials.refresh(Request())
            self._save_credentials(credentials)
        except Exception as exc:
            raise RuntimeError("La session Gmail a expiré. Reconnectez le compte.") from exc

    def access_token(self) -> str:
        with self._lock:
            credentials = self._load_credentials()
            if not credentials:
                raise RuntimeError("Connectez d'abord votre compte Gmail.")
            if not credentials.valid:
                if not credentials.refresh_token:
                    raise RuntimeError("La session Gmail a expiré. Reconnectez le compte.")
                self._refresh(credentials)
            return str(credentials.token)

    def disconnect(self) -> None:
        with self._lock:
            self.settings.google_token_path.unlink(missing_ok=True)
            self._last_error = None


class GmailMailClient:
    def __init__(self, auth: GoogleAuth):
        self.auth = auth

    def fetch_messages(self, since: str, limit: int) -> list[dict[str, Any]]:
        since_date = date.fromisoformat(since)
        since_utc = datetime.combine(since_date, time.min, tzinfo=timezone.utc)
        headers = {"Authorization": f"Bearer {self.auth.access_token()}", "Accept": "application/json"}
        references: list[dict[str, Any]] = []
        page_token: str | None = None

        with httpx.Client(timeout=30.0, follow_redirects=False) as client:
            while len(references) < limit:
                params: dict[str, Any] = {
                    "maxResults": min(500, limit - len(references)),
                    "q": f"after:{int(since_utc.timestamp())}",
                    "includeSpamTrash": "false",
                }
                if page_token:
                    params["pageToken"] = page_token
                response = client.get(GMAIL_MESSAGES_URL, params=params, headers=headers)
                response.raise_for_status()
                payload = response.json()
                references.extend(payload.get("messages", []))
                page_token = payload.get("nextPageToken")
                if not page_token:
                    break

            messages = [
                self._fetch_message(client, reference["id"], headers)
                for reference in references[:limit]
                if reference.get("id")
            ]
        return messages

    @staticmethod
    def _fetch_message(client: httpx.Client, message_id: str, headers: dict[str, str]) -> dict[str, Any]:
        response = client.get(
            f"{GMAIL_MESSAGES_URL}/{message_id}",
            params=[
                ("format", "metadata"),
                ("metadataHeaders", "From"),
                ("metadataHeaders", "Subject"),
            ],
            headers=headers,
        )
        response.raise_for_status()
        return GmailMailClient.message_to_email(response.json())

    @staticmethod
    def message_to_email(message: dict[str, Any]) -> dict[str, Any]:
        raw_headers = (message.get("payload") or {}).get("headers") or []
        mail_headers = {
            str(header.get("name", "")).lower(): str(header.get("value", ""))
            for header in raw_headers
        }
        sender_name, sender_address = parseaddr(_decode_mail_header(mail_headers.get("from", "")))
        internal_date = message.get("internalDate")
        received_at = ""
        if internal_date:
            received_at = datetime.fromtimestamp(int(internal_date) / 1000, tz=timezone.utc).isoformat()
        return {
            "graph_id": str(message.get("id", "")),
            "sender_name": sender_name or sender_address or "Expéditeur inconnu",
            "sender_address": sender_address,
            "subject": _decode_mail_header(mail_headers.get("subject", "")) or "(Sans objet)",
            "body_preview": html.unescape(str(message.get("snippet") or ""))[:4000],
            "received_at": received_at,
        }
