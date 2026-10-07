from __future__ import annotations

import html
import base64
import imaplib
import re
import ssl
from contextlib import contextmanager
from datetime import date, datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime, parseaddr
from html.parser import HTMLParser
from typing import Any


def encode_mailbox(value: str) -> str:
    """IMAP's modified UTF-7 folder encoding, including a literal ampersand."""
    result, pending = [], []

    def flush():
        if pending:
            encoded = base64.b64encode("".join(pending).encode("utf-16-be")).decode().rstrip("=").replace("/", ",")
            result.append(f"&{encoded}-")
            pending.clear()

    for char in value:
        if 32 <= ord(char) <= 126:
            flush()
            result.append("&-" if char == "&" else char)
        else:
            pending.append(char)
    flush()
    return "".join(result)


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"br", "p", "div", "li"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


class ImapMailClient:
    def __init__(self, account: dict[str, Any], password: str, known_ids: set[str] | None = None):
        self.account = account
        self.password = password
        self.known_ids = known_ids or set()

    @contextmanager
    def connection(self):
        client = None
        try:
            context = ssl.create_default_context()
            if self.account["security"] == "ssl":
                client = imaplib.IMAP4_SSL(self.account["host"], self.account["port"], ssl_context=context, timeout=30)
            else:
                client = imaplib.IMAP4(self.account["host"], self.account["port"], timeout=30)
            # imaplib's timeout argument only bounds connection establishment.
            client.sock.settimeout(30)
            if self.account["security"] == "starttls":
                client.starttls(ssl_context=context)
            if client.login(self.account["username"], self.password)[0] != "OK":
                raise RuntimeError("Connexion IMAP refusée. Vérifiez l’identifiant et le mot de passe d’application.")
            mailbox = encode_mailbox(self.account["mailbox"]).replace("\\", "\\\\").replace('"', '\\"')
            status, _ = client.select(f'"{mailbox}"', readonly=True)
            if status != "OK":
                raise RuntimeError("Le dossier IMAP est inaccessible. Vérifiez le nom du dossier.")
            yield client
        except ssl.SSLCertVerificationError as exc:
            raise RuntimeError("Le certificat du serveur IMAP est invalide. Vérifiez l’adresse et le certificat du serveur.") from exc
        except imaplib.IMAP4.error as exc:
            raise RuntimeError("Connexion IMAP refusée. Vérifiez les paramètres et le mot de passe d’application.") from exc
        except (OSError, UnicodeError, ValueError) as exc:
            raise RuntimeError("Le serveur IMAP est inaccessible. Vérifiez l’adresse, le port et le mode TLS.") from exc
        finally:
            if client is not None:
                try:
                    client.logout()
                except (OSError, imaplib.IMAP4.error):
                    pass

    def test_connection(self) -> None:
        with self.connection():
            pass

    def fetch_messages(self, since: str, limit: int) -> list[dict[str, Any]]:
        since_date = date.fromisoformat(since)
        months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
        criterion = f"{since_date.day:02d}-{months[since_date.month - 1]}-{since_date.year}"
        messages = []
        with self.connection() as client:
            status, data = client.uid("search", None, "SINCE", criterion)
            if status != "OK":
                raise RuntimeError("La recherche IMAP a échoué. Réessayez l’analyse.")
            uids = (data[0] or b"").split() if data else []
            _, validity = client.response("UIDVALIDITY")
            epoch = (validity[0] or b"0").decode("ascii") if validity else "0"
            prefix = f"imap-{self.account['id']}:{self.account['mailbox']}:{epoch}:"
            unseen = [uid for uid in uids if prefix + uid.decode("ascii") not in self.known_ids]
            for uid in reversed(unseen[-limit:]):
                status, response = client.uid("fetch", uid, "(INTERNALDATE BODY.PEEK[])")
                if status != "OK":
                    raise RuntimeError("La lecture d’un message IMAP a échoué. Réessayez l’analyse.")
                literal = next((item for item in response if isinstance(item, tuple)), None)
                if literal is None:
                    continue  # A message can disappear between SEARCH and FETCH.
                messages.append(self.message_to_email(literal[1], uid.decode("ascii"), epoch, literal[0]))
        return messages

    def message_to_email(self, raw: bytes, uid: str, validity: str, metadata: bytes = b"") -> dict[str, Any]:
        message = BytesParser(policy=policy.default).parsebytes(raw)
        sender_name, sender_address = parseaddr(str(message.get("From", "")))
        body = message.get_body(preferencelist=("plain", "html"))
        preview = ""
        if body is not None and body.get_content_disposition() != "attachment":
            try:
                preview = body.get_content()
            except (LookupError, UnicodeError):
                preview = (body.get_payload(decode=True) or b"").decode("utf-8", errors="replace")
            if body.get_content_type() == "text/html":
                parser = TextExtractor()
                parser.feed(preview)
                preview = " ".join(parser.parts)
        received = None
        match = re.search(rb'INTERNALDATE "([^"\r\n]+)"', metadata)
        value = match.group(1).decode("ascii") if match else str(message.get("Date", ""))
        try:
            # RFC date parser also accepts IMAP dates once the month dashes are replaced.
            received = parsedate_to_datetime(value.replace("-", " ", 2) if match else value)
        except (ValueError, TypeError, OverflowError):
            pass
        received = received or datetime.now(timezone.utc)
        if received.tzinfo is None:
            received = received.replace(tzinfo=timezone.utc)
        return {
            "message_id": str(message.get("Message-ID", "")),
            "thread_key": (re.findall(r"<[^>]+>", str(message.get("References", ""))) or
                           re.findall(r"<[^>]+>", str(message.get("In-Reply-To", ""))) or
                           re.findall(r"<[^>]+>", str(message.get("Message-ID", ""))) or [None])[0],
            "graph_id": f"imap-{self.account['id']}:{self.account['mailbox']}:{validity}:{uid}",
            "sender_name": sender_name or sender_address or "Expéditeur inconnu",
            "sender_address": sender_address,
            "subject": str(message.get("Subject", "")) or "(sans objet)",
            "body_preview": " ".join(html.unescape(preview).split())[:2000],
            "received_at": received.astimezone(timezone.utc).isoformat(),
        }
