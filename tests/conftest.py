from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.auth import SecretStore, UserAuth
from app.classifier import DemoClassifier
from app.config import JULIA_MODEL, LAYA_MODEL, get_settings
from app.db import Database
from app.runner import RunManager


class NamedClassifier(DemoClassifier):
    def __init__(self, name, model):
        self.name = name
        self.model = model


@pytest.fixture
def api_app(tmp_path, monkeypatch):
    import app.main as main
    settings = replace(get_settings(), data_dir=tmp_path, database_path=tmp_path / "mail.sqlite3",
                       laya_backend="demo", laya_model=LAYA_MODEL, julia_model=JULIA_MODEL, secure_cookies=False)
    db = Database(settings.database_path)
    classifier = DemoClassifier()
    models = {"julia-pytorch": NamedClassifier("julia-pytorch", JULIA_MODEL),
              "laya-pytorch": NamedClassifier("laya-pytorch", LAYA_MODEL)}
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "database", db)
    monkeypatch.setattr(main, "classifier", classifier)
    monkeypatch.setattr(main, "user_auth", UserAuth(db))
    monkeypatch.setattr(main, "secrets_store", SecretStore(tmp_path / "imap.key"))
    monkeypatch.setattr(main, "runner", RunManager(db, classifier, {}, provider_factory=main.provider_for, classifiers=models))
    return main


@pytest.fixture
def clients(api_app):
    with TestClient(api_app.app, headers={"X-Mailaya-Request": "1"}) as alice, TestClient(api_app.app, headers={"X-Mailaya-Request": "1"}) as bob, TestClient(api_app.app, headers={"X-Mailaya-Request": "1"}) as guest:
        yield alice, bob, guest


def register(client, username):
    response = client.post("/api/users", json={"username": username, "password": "test-password-12345"})
    assert response.status_code == 201, response.text
    return response.json()["user"]
