import multiprocessing
import os
import time
from dataclasses import replace

import pytest

from app.classifier import ClassifierLoadError, DemoClassifier
from app.config import get_settings
from app.db import Database
from app.inference import ProcessClassifier
from app.runner import RunManager
from test_classifier import sample_email
from test_runner import wait_for_terminal_state


class WorkerClassifier(DemoClassifier):
    def __init__(self, settings):
        self.mode = settings.laya_model
        self.marker = settings.data_dir / "worker-started"

    def classify(self, email):
        if self.mode == "load-error":
            raise ClassifierLoadError("modèle absent")
        if self.mode == "crash":
            os._exit(7)
        if self.mode == "message-error":
            raise ValueError("message invalide")
        if self.mode == "block" and not self.marker.exists():
            self.marker.write_text(str(os.getpid()))
            time.sleep(60)
        result = super().classify(email)
        result["worker_pid"] = os.getpid()
        result["input_fields"] = sorted(email)
        result["calls"] = getattr(self, "calls", 0) + 1
        self.calls = result["calls"]
        return result


def worker_factory(settings):
    return WorkerClassifier(settings)


def make_worker(tmp_path, mode="normal"):
    settings = replace(get_settings(), data_dir=tmp_path, database_path=tmp_path / "mail.sqlite3",
                       laya_backend="laya", laya_model=mode)
    return ProcessClassifier(settings, factory=worker_factory)


def wait_until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("condition was not reached")
        time.sleep(0.02)


def test_spawn_reuses_model_within_batch_and_exits_on_unload(tmp_path):
    worker = make_worker(tmp_path)
    worker.begin_run()
    try:
        email = sample_email(password="must-not-reach-worker", user_id=123)
        first, second = worker.classify(email), worker.classify(email)
        child = worker._process
        assert first["worker_pid"] != os.getpid()
        assert second["worker_pid"] == first["worker_pid"]
        assert second["calls"] == 2
        assert "password" not in first["input_fields"] and "user_id" not in first["input_fields"]
    finally:
        worker.unload()
    assert worker._process is None and child not in multiprocessing.active_children()
    worker.begin_run()
    try:
        assert worker.classify(sample_email())["calls"] == 1
    finally:
        worker.unload()


def test_manager_completes_only_after_worker_has_exited(tmp_path):
    worker = make_worker(tmp_path)
    manager = RunManager(Database(tmp_path / "mail.sqlite3"), worker, {})
    try:
        manager.start("demo", "2026-09-01", 3)
        payload = wait_for_terminal_state(manager, timeout=10)
        assert payload["run"]["processed"] == 3 and payload["run"]["failed"] == 0
        assert worker._process is None
    finally:
        manager.shutdown()


@pytest.mark.parametrize("mode,expected", [("load-error", "modèle absent"), ("crash", "processus d’inférence")])
def test_worker_failure_stops_batch_without_losing_pending_messages(tmp_path, mode, expected):
    worker = make_worker(tmp_path, mode)
    manager = RunManager(Database(tmp_path / "mail.sqlite3"), worker, {})
    try:
        manager.start("demo", "2026-09-01", 3)
        payload = wait_for_terminal_state(manager, timeout=10)
        assert payload["run"]["status"] == "failed" and expected in payload["run"]["error"]
        assert payload["run"]["processed"] == payload["run"]["failed"] == 0
        assert all(email["status"] == "pending" for email in payload["emails"])
        assert worker._process is None
    finally:
        manager.shutdown()


def test_message_failure_does_not_kill_the_batch(tmp_path):
    worker = make_worker(tmp_path, "message-error")
    manager = RunManager(Database(tmp_path / "mail.sqlite3"), worker, {})
    try:
        manager.start("demo", "2026-09-01", 3)
        payload = wait_for_terminal_state(manager, timeout=10)
        assert payload["run"]["status"] == "complete" and payload["run"]["failed"] == 3
        assert worker._process is None
    finally:
        manager.shutdown()


def test_pause_kills_busy_worker_and_resume_keeps_pending_message(tmp_path):
    worker = make_worker(tmp_path, "block")
    manager = RunManager(Database(tmp_path / "mail.sqlite3"), worker, {})
    try:
        run_id = manager.start("demo", "2026-09-01", 3)
        wait_until(lambda: (tmp_path / "worker-started").exists())
        manager.pause(run_id)
        wait_until(lambda: worker._process is None)
        paused = manager.dashboard()
        assert paused["run"]["status"] == "paused" and paused["run"]["processed"] == paused["run"]["failed"] == 0
        manager.resume(run_id)
        payload = wait_for_terminal_state(manager, timeout=10)
        assert payload["run"]["id"] == run_id and payload["run"]["processed"] == 3
        assert payload["run"]["failed"] == 0 and worker._process is None
    finally:
        manager.shutdown()


def test_immediate_resume_during_worker_cleanup_relaunches_same_run(tmp_path):
    worker = make_worker(tmp_path, "block")
    manager = RunManager(Database(tmp_path / "mail.sqlite3"), worker, {})
    try:
        run_id = manager.start("demo", "2026-09-01", 3)
        wait_until(lambda: (tmp_path / "worker-started").exists())
        manager.pause(run_id)
        manager.resume(run_id)
        payload = wait_for_terminal_state(manager, timeout=10)
        assert payload["run"]["id"] == run_id and payload["run"]["processed"] == 3
        assert payload["run"]["failed"] == 0 and worker._process is None
    finally:
        manager.shutdown()


def test_service_shutdown_stops_inference_and_leaves_run_resumable(tmp_path):
    worker = make_worker(tmp_path, "block")
    manager = RunManager(Database(tmp_path / "mail.sqlite3"), worker, {})
    manager.start("demo", "2026-09-01", 3)
    wait_until(lambda: (tmp_path / "worker-started").exists())
    manager.shutdown()
    assert worker._process is None
    assert manager.dashboard()["run"]["status"] == "paused"
    assert not any(thread.is_alive() for thread in manager._threads.values())
    with pytest.raises(RuntimeError, match="arrêt"):
        manager.start("demo", "2026-09-01", 1)


def test_waiting_user_cannot_cancel_another_users_worker(tmp_path):
    first_path, second_path = tmp_path / "first", tmp_path / "second"
    first_path.mkdir()
    second_path.mkdir()
    first, second = make_worker(first_path, "block"), make_worker(second_path, "block")
    second.name = "second-model"
    db = Database(tmp_path / "mail.sqlite3")
    with db.connect() as connection:
        connection.execute("INSERT INTO users(id, username, password_hash, created_at) VALUES (1, 'test', 'unused', '2026-10-07')")
    manager = RunManager(db, first, {}, classifiers={second.name: second})
    try:
        first_id = manager.start("demo", "2026-09-01", 1)
        wait_until(lambda: (first_path / "worker-started").exists())
        second_id = manager.start("demo", "2026-09-01", 1, user_id=1, model_backend=second.name)
        manager.pause(second_id)
        assert first._process.is_alive() and not first._cancelled.is_set()
        assert second._process is None
        manager.resume(second_id)
        manager.pause(first_id)
        wait_until(lambda: (second_path / "worker-started").exists())
        assert first._process is None
    finally:
        manager.shutdown()
    assert first._process is None and second._process is None
