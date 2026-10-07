import imaplib
import ssl
from email.message import EmailMessage
from types import SimpleNamespace

import pytest

from app.imap import ImapMailClient, encode_mailbox


ACCOUNT = {"id": 7, "host": "imap.example.test", "port": 993, "security": "ssl",
           "username": "alice@example.test", "mailbox": "INBOX"}


def mail_bytes(html=False):
    message = EmailMessage()
    message["From"] = "André <andre@example.test>"
    message["Subject"] = "Réunion à 14 h"
    message["Date"] = "Wed, 07 Oct 2026 14:00:00 +0200"
    if html:
        message.set_content("<p>Bonjour &amp; merci</p><script>hidden-script</script><style>hidden-style</style>", subtype="html")
    else:
        message.set_content("Merci de confirmer avant demain.")
        message.add_attachment(b"private attachment", maintype="application", subtype="octet-stream", filename="test.bin")
    return message.as_bytes()


class FakeServer:
    def __init__(self):
        self.calls = []
        self.sock = SimpleNamespace(settimeout=lambda value: self.calls.append(("timeout", value)))
        self.commands = []
        self.closed = False
    def starttls(self, ssl_context):
        self.calls.append(("starttls", ssl_context))
        return "OK", []
    def login(self, username, password):
        self.calls.append(("login", username, password))
        return "OK", []
    def select(self, mailbox, readonly=False):
        self.calls.append(("select", mailbox, readonly))
        return "OK", [b"3"]
    def response(self, key):
        assert key == "UIDVALIDITY"
        return key, [b"345"]
    def uid(self, command, *args):
        self.commands.append((command, args))
        if command == "search":
            return "OK", [b"1 2 3"]
        return "OK", [(b'1 (UID 3 INTERNALDATE "07-Oct-2026 14:00:00 +0200")', mail_bytes()), b")"]
    def logout(self):
        self.closed = True


@pytest.mark.parametrize("security,port", [("ssl", 993), ("starttls", 143)])
def test_imap_tls_readonly_uids_limit_and_normalization(monkeypatch, security, port):
    server = FakeServer()
    def connect(host, connected_port, **kwargs):
        assert host == ACCOUNT["host"] and connected_port == port
        assert kwargs["timeout"] == 30
        if security == "ssl":
            assert kwargs["ssl_context"].verify_mode == ssl.CERT_REQUIRED
            assert kwargs["ssl_context"].check_hostname
        return server
    monkeypatch.setattr(imaplib, "IMAP4_SSL" if security == "ssl" else "IMAP4", connect)
    messages = ImapMailClient({**ACCOUNT, "security": security, "port": port}, "private-password").fetch_messages("2026-10-01", 2)
    assert ("select", '"INBOX"', True) in server.calls
    assert server.commands == [("search", (None, "SINCE", "01-Oct-2026")),
                               ("fetch", (b"3", "(INTERNALDATE BODY.PEEK[])")),
                               ("fetch", (b"2", "(INTERNALDATE BODY.PEEK[])"))]
    if security == "starttls":
        assert [item[0] for item in server.calls].index("starttls") < [item[0] for item in server.calls].index("login")
        context = next(item[1] for item in server.calls if item[0] == "starttls")
        assert context.verify_mode == ssl.CERT_REQUIRED
    assert len(messages) == 2 and server.closed
    assert messages[0]["graph_id"] == "imap-7:INBOX:345:3"
    assert messages[0]["sender_name"] == "André"
    assert messages[0]["subject"] == "Réunion à 14 h"
    assert messages[0]["received_at"] == "2026-10-07T12:00:00+00:00"
    assert messages[0]["body_preview"] == "Merci de confirmer avant demain."
    assert "attachment" not in messages[0]["body_preview"]


def test_mime_html_and_international_folders():
    provider = ImapMailClient(ACCOUNT, "private-password")
    message = provider.message_to_email(mail_bytes(html=True), "1", "1")
    assert message["body_preview"] == "Bonjour & merci"
    assert message["received_at"] == "2026-10-07T12:00:00+00:00"
    assert encode_mailbox("Projets & été") == "Projets &- &AOk-t&AOk-"
    assert encode_mailbox("INBOX") == "INBOX"


def test_connection_errors_hide_server_responses_and_logout(monkeypatch):
    server = FakeServer()
    def login(*args):
        raise imaplib.IMAP4.error("private-password server internals")
    server.login = login
    monkeypatch.setattr(imaplib, "IMAP4_SSL", lambda *args, **kwargs: server)
    with pytest.raises(RuntimeError) as error:
        ImapMailClient(ACCOUNT, "private-password").test_connection()
    assert "private-password" not in str(error.value)
    assert "server internals" not in str(error.value)
    assert server.closed


def test_certificate_verification_is_never_disabled(monkeypatch):
    def connect(*args, **kwargs):
        raise ssl.SSLCertVerificationError("certificate mismatch")
    monkeypatch.setattr(imaplib, "IMAP4_SSL", connect)
    with pytest.raises(RuntimeError, match="certificat"):
        ImapMailClient(ACCOUNT, "private-password").test_connection()


def test_empty_mailbox_and_missing_message(monkeypatch):
    server = FakeServer()
    server.uid = lambda command, *args: ("OK", [b""]) if command == "search" else ("OK", [])
    monkeypatch.setattr(imaplib, "IMAP4_SSL", lambda *args, **kwargs: server)
    assert ImapMailClient(ACCOUNT, "private-password").fetch_messages("2026-10-01", 2) == []
    server.uid = lambda command, *args: ("OK", [b"1"]) if command == "search" else ("OK", [])
    assert ImapMailClient(ACCOUNT, "private-password").fetch_messages("2026-10-01", 2) == []
