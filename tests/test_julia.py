import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.classifier import (
    CATEGORIES, QUESTIONS, ClassifierLoadError, DemoClassifier,
    JuliaClassifier, LayaClassifier, build_classifier,
)
from app.config import JULIA_MODEL, JULIA_REVISION, Settings, get_settings
from app.db import Database
from app.runner import RunManager
from test_classifier import sample_email
from test_runner import wait_for_terminal_state


@pytest.fixture
def settings(tmp_path):
    return Settings(
        project_root=tmp_path, data_dir=tmp_path,
        database_path=tmp_path / "mailaya.sqlite3",
        laya_backend="julia", laya_model="convaiinnovations/laya-multilingual",
        max_emails_per_run=500,
        host="127.0.0.1", port=8000,
    )


@pytest.fixture
def runtime(monkeypatch):
    calls = {"loads": [], "downloads": [], "predictions": []}

    def predict(*, state, questions):
        calls["predictions"].append((state, questions))
        assert questions == QUESTIONS
        assert state["contenu"]
        probabilities = {key: (0.84 if key == "Achats" else 0.02) for key in CATEGORIES}
        return {"answers": {
            "category": {"type": "choice", "choice": "Achats", "probabilities": probabilities},
            "priority": {"type": "score", "score": 1.5},
            "spam": {"type": "noul", "noul": 0.025},
            "action": {"type": "noul", "noul": 0.875},
        }}

    def load_model(checkpoint, **kwargs):
        calls["loads"].append((checkpoint, kwargs))
        return SimpleNamespace(predict=predict)

    def snapshot_download(**kwargs):
        calls["downloads"].append(kwargs)
        return "/cached/julia"

    monkeypatch.setitem(sys.modules, "julia", SimpleNamespace(load_model=load_model))
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=snapshot_download))
    return calls


def test_julia_preserves_scores_and_loads_once(settings, runtime):
    classifier = JuliaClassifier(settings)
    result = classifier.classify(sample_email())
    classifier.classify(sample_email())

    assert result["category"] == "Achats"
    assert set(result["category_scores"]) == set(CATEGORIES)
    assert sum(result["category_scores"].values()) == pytest.approx(1)
    assert result["priority_score"] == 50
    assert result["spam_score"] == 2.5
    assert result["action_score"] == 87.5
    assert result["duration_ms"] >= 0
    assert len(runtime["loads"]) == len(runtime["downloads"]) == 1
    assert runtime["downloads"][0]["repo_id"] == JULIA_MODEL
    assert runtime["downloads"][0]["revision"] == JULIA_REVISION
    assert runtime["loads"][0] == ("/cached/julia", {
        "device": "cpu", "backend": "torch", "strict_encoding": True,
        "max_length": 8192, "head_length": 512, "marker_only_head": False,
    })


def test_local_checkpoint_never_downloads(settings, runtime, tmp_path):
    classifier = JuliaClassifier(replace(settings, julia_model=str(tmp_path)))
    classifier.classify(sample_email())
    assert runtime["downloads"] == []
    assert runtime["loads"][0][0] == str(tmp_path.resolve())


def test_missing_runtime_stops_the_batch_with_installation_help(settings, monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "julia", None)
    manager = RunManager(Database(tmp_path / "missing.sqlite3"), JuliaClassifier(settings), {})
    manager.start("demo", "2026-09-01", 3)
    payload = wait_for_terminal_state(manager)
    assert payload["run"]["status"] == "failed"
    assert "uv sync --extra julia" in payload["run"]["error"]
    assert payload["run"]["processed"] == payload["run"]["failed"] == 0
    assert all(email["status"] == "pending" for email in payload["emails"])


def test_download_failure_is_explicit_and_retry_can_succeed(settings, runtime, monkeypatch):
    hub = sys.modules["huggingface_hub"]
    original = hub.snapshot_download
    monkeypatch.setattr(hub, "snapshot_download", lambda **_: (_ for _ in ()).throw(OSError("offline")))
    classifier = JuliaClassifier(settings)
    with pytest.raises(ClassifierLoadError, match="offline"):
        classifier.classify(sample_email())
    monkeypatch.setattr(hub, "snapshot_download", original)
    assert classifier.classify(sample_email())["category"] == "Achats"


@pytest.mark.parametrize("system,machine,backend,expected", [
    ("Linux", "x86_64", "auto", JuliaClassifier),
    ("Linux", "aarch64", "auto", JuliaClassifier),
    ("Darwin", "arm64", "auto", JuliaClassifier),
    ("Darwin", "arm64", "julia", JuliaClassifier),
    ("Linux", "x86_64", "demo", DemoClassifier),
    ("Darwin", "arm64", "laya", LayaClassifier),
])
def test_backend_selection(settings, monkeypatch, system, machine, backend, expected):
    monkeypatch.setattr("app.config.platform.system", lambda: system)
    monkeypatch.setattr("app.config.platform.machine", lambda: machine)
    assert isinstance(build_classifier(replace(settings, laya_backend=backend)), expected)


def test_linux_auto_does_not_silently_use_demo_when_runtime_is_missing(settings, monkeypatch):
    monkeypatch.setattr("app.config.platform.system", lambda: "Linux")
    assert isinstance(build_classifier(replace(settings, laya_backend="auto")), JuliaClassifier)


def test_invalid_backend_is_rejected(settings):
    with pytest.raises(ValueError, match="LAYA_BACKEND"):
        build_classifier(replace(settings, laya_backend="julai"))


def test_julia_configuration_does_not_reuse_mlx_model(monkeypatch, tmp_path):
    monkeypatch.setattr("app.config._load_dotenv", lambda _: None)
    monkeypatch.setenv("LAYA_MAIL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LAYA_MODEL", "some/mlx-checkpoint")
    for name in ("JULIA_MODEL", "JULIA_REVISION", "JULIA_DEVICE"):
        monkeypatch.delenv(name, raising=False)
    assert get_settings().julia_model == JULIA_MODEL
    assert get_settings().julia_revision == JULIA_REVISION
    monkeypatch.setenv("JULIA_MODEL", str(tmp_path))
    assert get_settings().julia_revision is None


def test_julia_api_and_sqlite_pipeline(settings, runtime, monkeypatch):
    import app.main as main
    classifier = JuliaClassifier(settings)
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "classifier", classifier)
    monkeypatch.setattr(main, "runner", RunManager(Database(settings.database_path), classifier, {}))
    from app.auth import UserAuth
    monkeypatch.setattr(main, "user_auth", UserAuth(main.runner.db))
    with TestClient(main.app, headers={"X-Mailaya-Request": "1"}) as client:
        health = client.get("/api/health").json()
        assert health["backend"] == "julia-pytorch"
        assert health["model"] == JULIA_MODEL
        response = client.post("/api/runs", json={
            "source": "demo", "since_date": "2026-09-01", "limit": 3,
        })
        assert response.status_code == 202
        payload = wait_for_terminal_state(main.runner)
        assert payload["run"]["processed"] == 3
        assert payload["run"]["failed"] == 0
        assert payload["run"]["model_backend"] == "julia-pytorch"
        assert all(email["category"] == "Achats" for email in payload["emails"])
        dashboard = client.get("/api/dashboard").json()
        assert dashboard["configuration"]["model"] == JULIA_MODEL
        assert len(runtime["loads"]) == 1
