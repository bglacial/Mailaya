import hashlib
import time
from dataclasses import replace

import pytest

from app.auth import SESSION_COOKIE
from app.config import JULIA_MODEL, LAYA_MODEL
from conftest import register


ACCOUNT = {"name": "Personnel", "host": "imap.example.test", "port": 993, "security": "ssl",
           "username": "alice@example.test", "password": "imap-test-secret", "mailbox": "INBOX"}


def wait_dashboard(client):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        payload = client.get("/api/dashboard").json()
        if payload.get("run") and payload["run"]["status"] in {"complete", "empty", "failed"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("analysis did not finish")


def start_demo(client, model="julia"):
    response = client.post("/api/runs", json={"source": "demo", "since_date": "2026-10-01", "limit": 2, "model": model})
    assert response.status_code == 202, response.text
    return response.json()["run_id"]


def test_public_demo_and_private_results_are_separate(api_app, clients):
    alice, bob, guest = clients
    a = register(alice, "Alice")
    register(bob, "Bob")
    run_id = start_demo(alice)
    assert wait_dashboard(alice)["run"]["user_id"] == a["id"]
    for client in (bob, guest):
        assert client.get("/api/dashboard").json()["emails"] == []
        assert client.get("/api/dashboard").json()["run"] is None
        assert client.post(f"/api/runs/{run_id}/pause").status_code == 404
        assert client.post(f"/api/runs/{run_id}/resume").status_code == 404
        assert client.delete("/api/results").status_code == 204
    assert len(alice.get("/api/dashboard").json()["emails"]) == 2
    start_demo(guest, "laya")
    public = wait_dashboard(guest)
    assert public["run"]["user_id"] is None
    assert public["run"]["source"] == "demo"
    assert len(alice.get("/api/dashboard").json()["emails"]) == 2
    assert bob.get("/api/dashboard").json()["run"] is None


@pytest.mark.parametrize("model,expected", [("julia", JULIA_MODEL), ("laya", LAYA_MODEL)])
@pytest.mark.parametrize("signed_in", [False, True])
def test_model_selection_in_both_modes(clients, model, expected, signed_in):
    client = clients[0]
    if signed_in:
        register(client, "Alice")
    start_demo(client, model)
    payload = wait_dashboard(client)
    assert payload["run"]["model"] == expected
    assert payload["run"]["model_backend"] == f"{model}-pytorch"
    assert payload["configuration"]["model"] == expected
    assert {entry["model"] for entry in payload["configuration"]["models"]} == {JULIA_MODEL, LAYA_MODEL}


def test_imap_management_is_private_and_secrets_are_encrypted(api_app, clients):
    alice, bob, guest = clients
    a = register(alice, "Alice")
    register(bob, "Bob")
    response = alice.post("/api/imap/accounts", json=ACCOUNT)
    assert response.status_code == 201
    account = response.json()["account"]
    account_id = account["id"]
    assert "password" not in response.text and "imap-test-secret" not in response.text
    saved = api_app.runner.db.imap_account(account_id, a["id"])
    assert saved["password_encrypted"] != ACCOUNT["password"]
    assert api_app.secrets_store.decrypt(saved["password_encrypted"]) == ACCOUNT["password"]
    assert ACCOUNT["password"].encode() not in api_app.settings.database_path.read_bytes()
    assert api_app.settings.database_path.stat().st_mode & 0o777 == 0o600
    assert (api_app.settings.data_dir / "imap.key").stat().st_mode & 0o777 == 0o600
    assert len(alice.get("/api/imap/accounts").json()["accounts"]) == 1
    assert bob.get("/api/imap/accounts").json()["accounts"] == []
    assert guest.get("/api/imap/accounts").status_code == 401
    for method, path in [("put", ""), ("delete", ""), ("post", "/test")]:
        response = getattr(bob, method)(f"/api/imap/accounts/{account_id}{path}", **({"json": ACCOUNT} if method == "put" else {}))
        assert response.status_code == 404
    for client in (bob, guest):
        assert client.get("/api/dashboard").json()["imap_accounts"] == []
        response = client.post("/api/runs", json={"source": "imap", "imap_account_id": account_id, "since_date": "2026-10-01", "limit": 1})
        assert response.status_code == (404 if client is bob else 401)
    response = alice.put(f"/api/imap/accounts/{account_id}", json={**ACCOUNT, "name": "Bureau", "password": None})
    assert response.status_code == 200
    assert api_app.runner.db.imap_account(account_id, a["id"])["password_encrypted"] == saved["password_encrypted"]
    assert alice.delete(f"/api/imap/accounts/{account_id}").status_code == 204
    assert alice.get("/api/imap/accounts").json()["accounts"] == []


def test_imap_test_and_analysis_use_only_the_owners_credentials(api_app, clients, monkeypatch):
    alice, bob, guest = clients
    register(alice, "Alice")
    register(bob, "Bob")
    calls = []
    class Provider:
        def __init__(self, account, password):
            calls.append((account["user_id"], password))
        def test_connection(self):
            pass
        def fetch_messages(self, since, limit):
            return [{"graph_id": "imap-1", "sender_name": "Camille", "sender_address": "camille@example.test",
                     "subject": "Réponse attendue", "body_preview": "Pouvez-vous confirmer avant demain ?", "received_at": "2026-10-07T08:00:00+00:00"}]
    monkeypatch.setattr(api_app, "ImapMailClient", Provider)
    account_id = alice.post("/api/imap/accounts", json=ACCOUNT).json()["account"]["id"]
    assert bob.post(f"/api/imap/accounts/{account_id}/test").status_code == 404
    assert not calls
    assert alice.post(f"/api/imap/accounts/{account_id}/test").json()["status"] == "connected"
    response = alice.post("/api/runs", json={"source": "imap", "imap_account_id": account_id, "since_date": "2026-10-01", "limit": 1, "model": "laya"})
    assert response.status_code == 202
    payload = wait_dashboard(alice)
    assert payload["run"]["processed"] == 1
    assert payload["run"]["model"] == LAYA_MODEL
    assert payload["emails"][0]["subject"] == "Réponse attendue"
    assert len(calls) == 2
    assert bob.get("/api/dashboard").json()["emails"] == []
    assert guest.get("/api/dashboard").json()["emails"] == []


def test_sessions_passwords_logout_and_password_change(api_app, clients):
    alice, other, guest = clients
    a = register(alice, "Alice")
    assert other.post("/api/login", json={"username": "ALICE", "password": "test-password-12345"}).status_code == 200
    token = alice.cookies.get(SESSION_COOKIE)
    with api_app.runner.db.connect() as connection:
        row = connection.execute("SELECT * FROM users WHERE id=?", (a["id"],)).fetchone()
        assert row["password_hash"].startswith("scrypt$") and "test-password" not in row["password_hash"]
        stored = connection.execute("SELECT token_hash FROM sessions").fetchall()
        assert token not in [item[0] for item in stored]
        assert hashlib.sha256(token.encode()).hexdigest() in [item[0] for item in stored]
    cookie = alice.post("/api/login", json={"username": "alice", "password": "test-password-12345"}).headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert other.post("/api/login", json={"username": "alice", "password": "wrong-password-123"}).status_code == 401
    response = alice.put("/api/password", json={"current_password": "test-password-12345", "new_password": "updated-password-12345"})
    assert response.status_code == 200
    assert other.get("/api/dashboard").status_code == 401
    assert alice.get("/api/session").json()["user"]["id"] == a["id"]
    assert alice.post("/api/logout").status_code == 204
    assert alice.get("/api/session").json()["user"] is None
    assert alice.get("/api/imap/accounts").status_code == 401
    assert alice.post("/api/login", json={"username": "alice", "password": "test-password-12345"}).status_code == 401
    assert alice.post("/api/login", json={"username": "alice", "password": "updated-password-12345"}).status_code == 200


def test_invalid_sessions_csrf_and_validation_do_not_expose_secrets(api_app, clients):
    alice, bob, guest = clients
    secret = "tiny-secret"
    assert alice.post("/api/users", json={"username": "Alice", "password": secret}).status_code == 422
    assert secret not in alice.post("/api/users", json={"username": "Alice", "password": secret}).text
    register(alice, "Alice")
    assert bob.post("/api/users", json={"username": "ALICE", "password": "test-password-12345"}).status_code == 409
    assert alice.post("/api/logout", headers={"X-Mailaya-Request": ""}).status_code == 403
    assert alice.post("/api/logout", headers={"Origin": "https://attacker.example"}).status_code == 403
    assert alice.get("/api/session").json()["user"]
    assert alice.get("/api/dashboard").headers["cache-control"] == "no-store"
    guest.cookies.set(SESSION_COOKIE, "fabricated-session", domain="testserver.local", path="/")
    assert guest.get("/api/dashboard").status_code == 401
    assert guest.get("/api/imap/accounts", headers={"X-User-Id": "1"}).status_code == 401
    assert guest.post("/api/logout").status_code == 204
    assert guest.get("/api/dashboard").status_code == 200


def test_session_expiry_and_secure_cookie(api_app, clients):
    alice, _, _ = clients
    register(alice, "Alice")
    with api_app.runner.db.connect() as connection:
        connection.execute("UPDATE sessions SET expires_at=0")
    assert alice.get("/api/session").json()["user"] is None
    assert alice.get("/api/imap/accounts").status_code == 401
    api_app.settings = replace(api_app.settings, secure_cookies=True)
    response = alice.post("/api/login", json={"username": "alice", "password": "test-password-12345"})
    assert "secure" in response.headers["set-cookie"].lower()


def test_old_accounts_and_removed_gmail_are_unavailable(api_app, clients):
    alice, _, guest = clients
    register(alice, "Alice")
    legacy = api_app.runner.db.create_run("legacy", "2026-09-01", 1, "demonstration")
    api_app.runner.db.add_messages(legacy, [{"graph_id": "old-private", "sender_name": "Private", "sender_address": "private@example.test", "subject": "SECRET", "body_preview": "old private data", "received_at": "2026-09-01"}])
    for client in (alice, guest):
        assert client.get("/api/dashboard").json()["emails"] == []
        assert client.post(f"/api/runs/{legacy}/pause").status_code == 404
        assert client.delete("/api/results").status_code == 204
    assert api_app.runner.db.get_run(legacy) is not None
    assert alice.post("/api/auth/google/start").status_code == 404
    assert alice.get("/api/auth/google/callback").status_code == 404
    assert "google" not in str(api_app.app.openapi())
    assert alice.post("/api/runs", json={"source": "gmail", "since_date": "2026-10-01", "limit": 1}).status_code == 422


def test_account_used_by_paused_run_cannot_be_changed(api_app, clients):
    alice, _, _ = clients
    a = register(alice, "Alice")
    account_id = alice.post("/api/imap/accounts", json=ACCOUNT).json()["account"]["id"]
    run_id = api_app.runner.db.create_run("imap", "2026-10-01", 1, "laya-pytorch", a["id"], account_id, LAYA_MODEL)
    api_app.runner.db.set_run(run_id, status="paused")
    assert alice.put(f"/api/imap/accounts/{account_id}", json=ACCOUNT).status_code == 409
    assert alice.delete(f"/api/imap/accounts/{account_id}").status_code == 409
    assert alice.delete("/api/results").status_code == 204
    assert alice.delete(f"/api/imap/accounts/{account_id}").status_code == 204


def test_pause_resume_preserves_model_and_concurrent_users_are_independent(api_app, clients, monkeypatch):
    import threading
    from app.classifier import DemoClassifier
    alice, bob, guest = clients
    a = register(alice, "Alice")
    b = register(bob, "Bob")
    entered = threading.Event()
    release = threading.Event()
    model = api_app.runner.classifiers["laya-pytorch"]
    def classify(email):
        entered.set()
        assert release.wait(5)
        return DemoClassifier().classify(email)
    monkeypatch.setattr(model, "classify", classify)
    try:
        run_id = start_demo(alice, "laya")
        assert entered.wait(3)
        assert alice.post(f"/api/runs/{run_id}/pause").status_code == 200
        assert bob.post(f"/api/runs/{run_id}/resume").status_code == 404
        # A paused worker still finishing a model call cannot be deleted underneath that call.
        assert alice.delete("/api/results").status_code == 409
        other_run = start_demo(bob, "julia")
        assert api_app.runner.db.get_run(other_run)["user_id"] == b["id"]
        assert alice.post(f"/api/runs/{run_id}/resume").status_code == 200
    finally:
        release.set()
    assert wait_dashboard(alice)["run"]["model"] == LAYA_MODEL
    assert wait_dashboard(bob)["run"]["model"] == JULIA_MODEL
    assert guest.get("/api/dashboard").json()["run"] is None
    assert api_app.runner.db.get_run(run_id)["user_id"] == a["id"]


def test_account_connection_failure_is_reported_without_credentials(api_app, clients, monkeypatch):
    alice, _, _ = clients
    register(alice, "Alice")
    account_id = alice.post("/api/imap/accounts", json=ACCOUNT).json()["account"]["id"]
    class FailedProvider:
        def __init__(self, *args):
            pass
        def test_connection(self):
            raise RuntimeError("Le serveur IMAP est inaccessible.")
    monkeypatch.setattr(api_app, "ImapMailClient", FailedProvider)
    response = alice.post(f"/api/imap/accounts/{account_id}/test")
    assert response.status_code == 400
    assert ACCOUNT["password"] not in response.text
    assert "inaccessible" in response.json()["detail"]


def test_reverse_proxy_subpath_preserves_csrf_sessions_and_assets(api_app):
    from fastapi.testclient import TestClient
    prefix = "/projects/mailaya"
    with TestClient(api_app.app, root_path=prefix, base_url="https://lab.example", headers={"X-Mailaya-Request": "1"}) as client:
        page = client.get(prefix + "/")
        assert page.status_code == 200
        assert f'content="{prefix}"' in page.text
        assert f'href="{prefix}/static/app.css?' in page.text
        response = client.post(prefix + "/api/users", json={"username": "Alice", "password": "test-password-12345"}, headers={"Origin": "https://lab.example"})
        assert response.status_code == 201
        assert f"Path={prefix}" in response.headers["set-cookie"]
        assert "Secure" in response.headers["set-cookie"]
        assert client.get(prefix + "/api/session").json()["user"]
        assert client.get(prefix + "/api/dashboard").headers["cache-control"] == "no-store"
        assert client.post(prefix + "/api/logout", headers={"Origin": "https://attacker.example"}).status_code == 403
        assert client.post(prefix + "/api/logout").status_code == 204
        assert client.get(prefix + "/api/session").json()["user"] is None
