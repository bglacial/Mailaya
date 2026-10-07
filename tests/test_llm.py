import json

import httpx
import pytest

from app.auth import SecretStore
from app.llm import LLMClient, validate_url


def client(tmp_path, protocol="omlx", secret=""):
    store = SecretStore(tmp_path / "key")
    return LLMClient({"base_url": "http://127.0.0.1:11435/v1", "model": "test", "protocol": protocol,
                      "allow_remote": False, "secret": store.encrypt(secret) if secret else ""}, store)


def transport(monkeypatch, handler):
    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real(transport=httpx.MockTransport(handler), **kwargs))


def test_omlx_discovers_chat_models_and_disables_thinking(tmp_path, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "chat"}, {"id": "Qwen-Embedding"}, {"id": "fishaudio-s2"}]})
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": '```json\n{"ok":true}\n```'}}]})
    transport(monkeypatch, handler)
    llm = client(tmp_path, secret="fake-test-secret")
    assert llm.models() == ["chat"]
    assert llm.complete_json("Return JSON", {"query": "devis"}) == {"ok": True}
    body = json.loads(calls[-1].content)
    assert body["chat_template_kwargs"]["enable_thinking"] is False
    assert body["max_tokens"] == 1200 and calls[-1].headers["Authorization"] == "Bearer fake-test-secret"


def test_ollama_native_contract_and_memory_release(tmp_path, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"models": [{"name": "local:small"}]})
        return httpx.Response(200, json={"done": True, "message": {"content": '{"ok":true}'}})
    transport(monkeypatch, handler)
    llm = client(tmp_path, protocol="ollama")
    assert llm.models() == ["local:small"]
    assert llm.complete_json("JSON", {})["ok"]
    body = json.loads(calls[-1].content)
    assert body["keep_alive"] == 0 and body["think"] is False and body["options"]["num_ctx"] == 8192
    assert calls[-1].url.path.endswith("/api/chat")


@pytest.mark.parametrize("response", [
    {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": "invalid"}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": "[]"}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": None}}]},
    {"choices": [None]},
    [],
])
def test_malformed_or_truncated_generation_is_not_success(tmp_path, monkeypatch, response):
    transport(monkeypatch, lambda request: httpx.Response(200, json=response))
    with pytest.raises(ValueError):
        client(tmp_path).complete_json("JSON", {})


def test_http_errors_do_not_reveal_provider_response_or_key(tmp_path, monkeypatch):
    transport(monkeypatch, lambda request: httpx.Response(401, text="private-provider-response-and-secret"))
    with pytest.raises(ValueError) as error:
        client(tmp_path, secret="fake-test-secret").models()
    assert "401" in str(error.value) and "private-provider" not in str(error.value) and "fake-test-secret" not in str(error.value)


@pytest.mark.parametrize("url", ["http://user:pass@127.0.0.1", "http://127.0.0.1?secret=abc", "http://169.254.169.254", "file:///etc/passwd"])
def test_endpoint_rejects_embedded_secrets_and_metadata(url):
    with pytest.raises(ValueError):
        validate_url(url, False)
