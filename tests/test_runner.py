import time

from app.classifier import DemoClassifier
from app.db import Database
from app.runner import RunManager


def wait_for_terminal_state(manager, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = manager.dashboard()
        if payload["run"]["status"] in {"complete", "empty", "failed"}:
            return payload
        time.sleep(0.02)
    raise AssertionError("run did not finish")


def test_demo_run_is_persisted_end_to_end(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    manager = RunManager(database, DemoClassifier(), {})

    run_id = manager.start("demo", "2026-09-01", 3)
    payload = wait_for_terminal_state(manager)

    assert payload["run"]["id"] == run_id
    assert payload["run"]["status"] == "complete"
    assert payload["run"]["processed"] == 3
    assert len(payload["emails"]) == 3
    assert payload["metrics"]["average_ms"] > 0
    assert sum(payload["metrics"]["categories"].values()) == 3


def test_demo_run_can_process_all_500_messages(tmp_path, monkeypatch):
    database = Database(tmp_path / "demo-500.sqlite3")
    classifier = DemoClassifier()
    monkeypatch.setattr(classifier, "classify", lambda _: {
        "category": "Autre",
        "category_scores": {"Autre": 1.0},
        "priority_score": 0,
        "spam_score": 0,
        "action_score": 0,
        "duration_ms": 1,
    })
    manager = RunManager(database, classifier, {})

    manager.start("demo", "2026-09-01", 500)
    payload = wait_for_terminal_state(manager, timeout=10)

    assert payload["run"]["status"] == "complete"
    assert payload["run"]["total"] == 500
    assert payload["run"]["processed"] == 500
    assert len(payload["emails"]) == 500


class GmailFixture:
    def fetch_messages(self, since, limit):
        assert since == "2026-09-01"
        assert limit == 1
        return [
            {
                "graph_id": "gmail-1",
                "sender_name": "Camille",
                "sender_address": "camille@example.com",
                "subject": "Réponse attendue",
                "body_preview": "Pouvez-vous confirmer avant demain ?",
                "received_at": "2026-09-22T08:00:00+00:00",
            }
        ]


def test_gmail_source_uses_the_shared_analysis_pipeline(tmp_path):
    database = Database(tmp_path / "gmail.sqlite3")
    manager = RunManager(database, DemoClassifier(), {"gmail": GmailFixture()})

    manager.start("gmail", "2026-09-01", 1)
    payload = wait_for_terminal_state(manager)

    assert payload["run"]["status"] == "complete"
    assert payload["run"]["source"] == "gmail"
    assert payload["run"]["processed"] == 1
    assert payload["emails"][0]["graph_id"] == "gmail-1"
    assert payload["emails"][0]["action_score"] > 0
