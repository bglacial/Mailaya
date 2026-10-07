import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.classifier import ClassifierLoadError, LayaClassifier, QUESTIONS
from app.config import LAYA_MODEL, get_settings
from test_classifier import sample_email


def test_native_laya_uses_the_official_checkpoint_and_shared_questions(monkeypatch):
    calls = []
    predictions = []
    def predict(state, questions, **kwargs):
        predictions.append((state, questions, kwargs))
        return {"answers": {"category": {"choice": "Finance", "probabilities": {"Finance": 0.8, "Autre": 0.2}},
                            "priority": {"score": 1.5}, "spam": {"noul": 0.25}, "action": {"noul": 0.9}}}
    def load(model, **kwargs):
        calls.append((model, kwargs))
        return SimpleNamespace(predict=predict)
    monkeypatch.setitem(sys.modules, "laya", SimpleNamespace(load=load))
    classifier = LayaClassifier(replace(get_settings(), laya_model=LAYA_MODEL, laya_device="cpu"))
    result = classifier.classify(sample_email())
    classifier.classify(sample_email())
    assert calls == [(LAYA_MODEL, {"device": "cpu"})]
    assert predictions[0][1] is QUESTIONS
    assert predictions[0][2] == {"max_len": 8192}
    assert result["category"] == "Finance"
    assert result["priority_score"] == 50
    assert result["spam_score"] == 25
    assert result["action_score"] == 90


def test_missing_native_laya_reports_installation_help(monkeypatch):
    monkeypatch.setitem(sys.modules, "laya", None)
    with pytest.raises(ClassifierLoadError, match="uv sync --extra laya"):
        LayaClassifier(get_settings()).classify(sample_email())
