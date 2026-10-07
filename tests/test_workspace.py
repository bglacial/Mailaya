import json
import time
from datetime import datetime, timedelta, timezone

from conftest import register
from app.workspace import AccountOptions, MailFilters, Workspace
from app.workspace_api import WorkspaceScheduler


ACCOUNT = {"name": "Personnel", "host": "imap.example.test", "username": "alice@example.test", "password": "test-app-password"}


def wait(client, target=None):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        data = client.get("/api/dashboard").json()
        if data["run"] and (target is None or data["run"]["id"] == target) and data["run"]["status"] in {"complete", "failed", "empty"}:
            return data
        time.sleep(.02)
    raise AssertionError("Run timed out")


def demo(client, model="julia", limit=6):
    response = client.post("/api/runs", json={"since_date": "2020-01-01", "limit": limit, "model": model})
    assert response.status_code == 202, response.text
    return wait(client, response.json()["run_id"])


def options(client, account=0, **values):
    body = {**AccountOptions().model_dump(), **values}
    response = client.put(f"/api/workspace/accounts/{account}/options", json=body)
    assert response.status_code == 200, response.text
    return response


def test_workspace_requires_login_and_defaults_are_lightweight(clients):
    alice, bob, guest = clients
    assert guest.get("/api/workspace").status_code == 401
    register(alice, "Alice")
    data = alice.get("/api/workspace").json()
    assert not any(data["profiles"]["0"]["options"][key] for key in ("sync_enabled", "brief_enabled", "comparison_enabled", "natural_search_enabled", "llm_enabled"))
    assert alice.post("/api/workspace/brief", json={}).status_code == 400
    assert alice.post("/api/workspace/natural-search", json={"query": "mes mails"}).status_code == 400


def test_corrections_rules_followup_and_predictions_survive_new_run(api_app, clients):
    alice, bob, _ = clients
    user = register(alice, "Alice"); register(bob, "Bob")
    data = demo(alice)
    initial = data["emails"][0]
    assert alice.post("/api/workspace/rules", json={"name": "Client", "contains": initial["sender_address"], "category": "Client", "priority": 90}).status_code == 201
    email = alice.get(f'/api/workspace/messages/{initial["id"]}').json()
    assert email["effective_category"] == "Client" and email["category"] == initial["category"]
    assert alice.put(f'/api/workspace/messages/{email["id"]}', json={"category": "Personnel", "priority": 77, "task": "done"}).status_code == 200
    assert bob.get(f'/api/workspace/messages/{email["id"]}').status_code == 404
    assert bob.put(f'/api/workspace/messages/{email["id"]}', json={"category": "Intrusion"}).status_code == 404
    demo(alice)
    results = alice.get("/api/workspace/messages?task=done").json()
    assert results["total"] == 1
    corrected = results["emails"][0]
    assert corrected["effective_category"] == "Personnel" and corrected["decision_source"] == "manual"
    assert corrected["category"] == initial["category"]
    assert len(alice.get("/api/workspace/messages").json()["emails"]) == 6
    assert len(alice.get("/api/workspace").json()["history"]) == 2
    with api_app.runner.db.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM correction_events WHERE user_id=?", (user["id"],)).fetchone()[0] == 1


def test_snooze_date_and_automatic_return(api_app, clients):
    alice, _, _ = clients; user = register(alice, "Alice"); data = demo(alice)
    email = data["emails"][0]
    url = f'/api/workspace/messages/{email["id"]}'
    assert alice.put(url, json={"task": "snoozed"}).status_code == 400
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    assert alice.put(url, json={"task": "snoozed", "snoozed_until": future}).status_code == 200
    assert alice.get("/api/workspace/messages?task=snoozed").json()["total"] == 1
    past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    with api_app.runner.db.connect() as c:
        c.execute("UPDATE annotations SET payload=? WHERE user_id=?", (json.dumps({"task": "snoozed", "snoozed_until": past}), user["id"]))
    assert alice.get(url).json()["task"] == "todo"


def test_filters_views_exports_are_scoped_and_csv_is_safe(api_app, clients):
    alice, bob, _ = clients; register(alice, "Alice"); register(bob, "Bob")
    data = demo(alice)
    email = data["emails"][0]
    with api_app.runner.db.connect() as c:
        c.execute("UPDATE emails SET subject=? WHERE id=?", ("=HYPERLINK(\"https://example.test\")", email["id"]))
    filters = {"sender": email["sender_address"], "sort": "priority"}
    view = alice.post("/api/workspace/views", json={"name": "Client", "filters": filters}).json()["id"]
    assert alice.get("/api/workspace").json()["views"][0]["filters"]["sender"] == email["sender_address"]
    assert not bob.get("/api/workspace").json()["views"]
    assert bob.delete(f"/api/workspace/views/{view}").status_code == 404
    csv = alice.post("/api/workspace/export", json={"filters": filters}).text
    assert "'=HYPERLINK" in csv
    exported = alice.post("/api/workspace/export", json={"format": "json", "filters": filters}).json()
    assert all(e["sender_address"] == email["sender_address"] for e in exported)
    assert bob.post("/api/workspace/export", json={"format": "json"}).json() == []
    assert bob.get(f'/api/workspace/history/{data["run"]["id"]}').status_code == 404
    assert alice.get("/api/workspace/messages?priority_min=101").status_code == 422
    assert alice.get("/api/workspace/messages?sql=DROP").status_code == 422


def test_comparison_reuses_exact_imported_lot(clients):
    alice, bob, _ = clients; register(alice, "Alice"); register(bob, "Bob")
    initial = demo(alice)
    run_id = initial["run"]["id"]
    assert alice.post(f"/api/workspace/runs/{run_id}/compare").status_code == 400
    options(alice, comparison_enabled=True)
    compared = alice.post(f"/api/workspace/runs/{run_id}/compare")
    assert compared.status_code == 202, compared.text
    target = compared.json()["run_id"]; data = wait(alice, target)
    assert {e["graph_id"] for e in data["emails"]} == {e["graph_id"] for e in initial["emails"]}
    assert data["run"]["model_backend"] == "laya-pytorch"
    result = alice.get(f"/api/workspace/runs/{target}/comparison").json()
    assert result["compared"] == 6 and result["left_accuracy"] is None
    assert bob.get(f"/api/workspace/runs/{target}/comparison").status_code == 404


def test_conversation_groups_and_can_be_opened(api_app, clients):
    alice, _, _ = clients; register(alice, "Alice"); data = demo(alice)
    ids = [e["id"] for e in data["emails"][:2]]
    with api_app.runner.db.connect() as c:
        c.execute("UPDATE emails SET thread_key=? WHERE id IN (?,?)", ("<root@example.test>", *ids))
    results = alice.get("/api/workspace/messages?conversations=true").json()
    group = next(e for e in results["emails"] if e.get("conversation_count") == 2)
    opened = alice.get("/api/workspace/messages", params={"conversation": group["conversation"]}).json()
    assert len(opened["emails"]) == 2 and results["total"] == 5


def test_incremental_sync_skips_completed_same_model(api_app, clients, monkeypatch):
    alice, _, _ = clients; user = register(alice, "Alice")
    account = alice.post("/api/imap/accounts", json=ACCOUNT).json()["account"]["id"]
    seen = []
    class Provider:
        def __init__(self, account, password):
            self.known_ids = set()
        def fetch_messages(self, since, limit):
            seen.append(set(self.known_ids))
            message = {"graph_id": "imap-epoch-1", "sender_name": "Client", "sender_address": "client@example.test",
                       "subject": "Devis", "body_preview": "Répondre avant vendredi", "received_at": "2026-10-07T09:00:00+00:00"}
            return [] if message["graph_id"] in self.known_ids else [message]
    monkeypatch.setattr(api_app, "ImapMailClient", Provider)
    body = {"source": "imap", "imap_account_id": account, "since_date": "2026-10-01", "limit": 2, "model": "julia"}
    assert alice.post("/api/runs", json=body).status_code == 202
    assert wait(alice)["run"]["processed"] == 1
    assert alice.post("/api/runs", json=body).status_code == 202
    assert wait(alice)["run"]["status"] == "empty"
    assert seen == [set(), {"imap-epoch-1"}]
    assert Workspace(api_app.runner.db).known_ids(user["id"], account, "laya-pytorch") == set()


def test_account_options_and_connections_are_private(api_app, clients, monkeypatch):
    alice, bob, _ = clients; register(alice, "Alice"); register(bob, "Bob")
    account = alice.post("/api/imap/accounts", json=ACCOUNT).json()["account"]["id"]
    assert bob.put(f"/api/workspace/accounts/{account}/options", json={}).status_code == 404
    connection = {"name": "Local", "base_url": "http://127.0.0.1:11435/v1", "model": "test-model", "api_key": "test-api-secret"}
    created = alice.post("/api/workspace/connections", json=connection)
    assert created.status_code == 201, created.text
    connection_id = created.json()["id"]
    assert "test-api-secret" not in alice.get("/api/workspace").text
    assert bob.get(f"/api/workspace/connections/{connection_id}/models").status_code == 404
    assert bob.put("/api/workspace/accounts/0/options", json={"connection_id": connection_id}).status_code == 404
    options(alice, account, brief_enabled=True, connection_id=connection_id)
    assert not alice.get("/api/workspace").json()["profiles"]["0"]["options"]["brief_enabled"]
    with api_app.runner.db.connect() as c:
        saved = c.execute("SELECT secret FROM llm_connections").fetchone()[0]
        assert saved != "test-api-secret" and api_app.secrets_store.decrypt(saved) == "test-api-secret"
    assert alice.post("/api/workspace/connections", json={**connection, "base_url": "http://user:password@localhost/v1"}).status_code == 400


def test_brief_without_llm_is_cached_and_scoped(clients):
    alice, bob, _ = clients; register(alice, "Alice"); register(bob, "Bob"); demo(alice)
    options(alice, brief_enabled=True)
    first = alice.post("/api/workspace/brief", json={}).json()
    second = alice.post("/api/workspace/brief", json={}).json()
    assert first["mode"] == "local" and second["cached"]
    assert alice.get("/api/workspace/briefs/0").json()["briefs"]
    assert bob.get("/api/workspace/briefs/0").json()["briefs"] == []


def llm_setup(client):
    connection = client.post("/api/workspace/connections", json={"name": "Local", "model": "test-model"}).json()["id"]
    options(client, brief_enabled=True, llm_enabled=True, natural_search_enabled=True, connection_id=connection)


def test_natural_search_validates_filters_and_locks_scope(clients, monkeypatch):
    from app.llm import LLMClient
    alice, _, _ = clients; register(alice, "Alice"); demo(alice); llm_setup(alice)
    monkeypatch.setattr(LLMClient, "complete_json", lambda *args: {"filters": {"task": "todo", "sort": "priority"}, "interpretation": "À faire"})
    response = alice.post("/api/workspace/natural-search", json={"query": "Mails à faire"})
    assert response.status_code == 200, response.text
    assert response.json()["filters"]["task"] == "todo"
    for filters in ({"account_id": 123}, {"sql": "DROP TABLE users"}, {"priority_min": 999}):
        monkeypatch.setattr(LLMClient, "complete_json", lambda *args: {"filters": filters})
        assert alice.post("/api/workspace/natural-search", json={"query": "intrusion"}).status_code == 400


def test_brief_rejects_fabricated_message_references(clients, monkeypatch):
    from app.llm import LLMClient
    alice, _, _ = clients; register(alice, "Alice"); demo(alice); llm_setup(alice)
    monkeypatch.setattr(LLMClient, "complete_json", lambda *args: {"insights": [{"email_id": 999999, "summary": "Inventé"}]})
    assert alice.post("/api/workspace/brief", json={}).status_code == 400
    assert alice.get("/api/workspace/briefs/0").json()["briefs"] == []


def test_scheduler_is_opt_in_and_does_not_replace_paused_work(api_app, clients, monkeypatch):
    alice, _, _ = clients; user = register(alice, "Alice")
    account = alice.post("/api/imap/accounts", json=ACCOUNT).json()["account"]["id"]
    calls = []
    monkeypatch.setattr(api_app.runner, "start", lambda *args, **kwargs: calls.append((args, kwargs)) or 42)
    scheduler = WorkspaceScheduler(api_app)
    scheduler.tick(); assert not calls
    options(alice, account, sync_enabled=True)
    scheduler.tick(); assert len(calls) == 1 and calls[0][1]["incremental"]
    scheduler.tick(); assert len(calls) == 1
    run = api_app.runner.db.create_run("imap", "2026-10-01", 2, "julia-pytorch", user["id"], account)
    api_app.runner.db.set_run(run, status="paused")
    Workspace(api_app.runner.db).runtime(user["id"], account, last_sync=0)
    scheduler.tick(); assert len(calls) == 1


def test_migration_preserves_results_and_new_defaults(api_app, clients):
    from app.db import Database
    alice, _, _ = clients; user = register(alice, "Alice"); before = demo(alice)
    rebuilt = Database(api_app.runner.db.path)
    after = rebuilt.emails_for_run(before["run"]["id"])
    assert [e["graph_id"] for e in after] == [e["graph_id"] for e in before["emails"]]
    assert not Workspace(rebuilt).options(user["id"])["options"]["sync_enabled"]


def test_daily_scheduler_prepares_once_and_retries_errors_after_delay(api_app, clients, monkeypatch):
    import app.workspace_api as scheduler_api
    alice, _, _ = clients; user = register(alice, "Alice")
    options(alice, brief_enabled=True, brief_auto=True, brief_hour=0)
    calls = []
    def generate(*args):
        calls.append(args)
        if len(calls) == 1:
            raise ValueError("Modèle indisponible")
        return {}
    monkeypatch.setattr(scheduler_api, "generate_brief", generate)
    scheduler = WorkspaceScheduler(api_app)
    scheduler.tick(); scheduler.tick()
    assert len(calls) == 1
    store = Workspace(api_app.runner.db)
    assert store.options(user["id"])["runtime"]["brief_error"] == "Modèle indisponible"
    store.runtime(user["id"], 0, brief_attempt=0)
    scheduler.tick(); scheduler.tick()
    assert len(calls) == 2
    assert store.options(user["id"])["runtime"]["brief_error"] is None


def test_scheduler_keeps_running_after_unexpected_failure(api_app, monkeypatch, caplog):
    scheduler = WorkspaceScheduler(api_app)
    waits = iter([False, False, True])
    monkeypatch.setattr(scheduler.event, "wait", lambda _: next(waits))
    calls = []
    def tick():
        calls.append(True)
        if len(calls) == 1:
            raise RuntimeError("private exception detail")
    monkeypatch.setattr(scheduler, "tick", tick)
    scheduler.loop()
    assert len(calls) == 2
    assert "RuntimeError" in caplog.text and "private exception detail" not in caplog.text
