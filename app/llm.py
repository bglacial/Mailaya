"""Bounded, server-side generation. Credentials never reach the browser."""
from __future__ import annotations

import ipaddress
import json
import re
import socket
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from typing import Literal


class ConnectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="Mon serveur local", min_length=1, max_length=80)
    protocol: Literal["omlx", "ollama", "openai"] = "omlx"
    base_url: str = Field(default="http://127.0.0.1:11435/v1", max_length=500)
    model: str = Field(default="", max_length=200)
    api_key: SecretStr | None = Field(default=None, max_length=4096)
    allow_remote: bool = False


def validate_url(value: str, allow_remote: bool) -> str:
    parts = urlsplit(value.strip())
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Utilisez une URL HTTP(S) sans identifiants, paramètres ni fragment.")
    try:
        addresses = [ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(parts.hostname, parts.port or 80, type=socket.SOCK_STREAM)]
    except (OSError, ValueError):
        raise ValueError("L’adresse du serveur LLM ne peut pas être résolue.") from None
    if any(ip.is_link_local or ip.is_unspecified or ip.is_multicast for ip in addresses):
        raise ValueError("Cette adresse réseau n’est pas autorisée.")
    if not allow_remote and any(not (ip.is_loopback or ip.is_private) for ip in addresses):
        raise ValueError("Pour ce serveur externe, activez explicitement l’autorisation de traitement distant.")
    if allow_remote and parts.scheme != "https" and any(not (ip.is_loopback or ip.is_private) for ip in addresses):
        raise ValueError("Un serveur externe doit utiliser HTTPS.")
    return value.strip().rstrip("/")


class LLMClient:
    def __init__(self, connection, secrets_store):
        self.connection = connection
        self.url = validate_url(connection["base_url"], bool(connection["allow_remote"]))
        self.protocol = connection["protocol"]
        secret = secrets_store.decrypt(connection["secret"]) if connection.get("secret") else ""
        self.headers = {"Authorization": "Bearer " + secret} if secret else {}

    def request(self, method, path, payload=None):
        try:
            with httpx.Client(timeout=httpx.Timeout(180, connect=10), trust_env=False, follow_redirects=False) as client:
                response = client.request(method, self.url + path, headers=self.headers, json=payload)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError()
                return payload
        except httpx.HTTPStatusError as exc:
            raise ValueError(f"Le serveur LLM a refusé la requête (HTTP {exc.response.status_code}). Vérifiez le modèle, l’accès et la mémoire disponible.") from None
        except (httpx.HTTPError, ValueError):
            raise ValueError("Le serveur LLM est inaccessible ou sa réponse est invalide. Vérifiez son adresse et son état.") from None

    def models(self):
        payload = self.request("GET", "/api/tags" if self.protocol == "ollama" else "/models")
        items = payload.get("models", []) if self.protocol == "ollama" else payload.get("data", [])
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise ValueError("Le catalogue retourné par le serveur LLM est invalide.")
        models = [str(item.get("name") or item.get("id")) for item in items if item.get("name") or item.get("id")]
        # oMLX exposes non-chat models in the same catalogue.
        return sorted(m for m in models if not any(tag in m.lower() for tag in ("embedding", "fishaudio", "tts")))

    def complete_json(self, system: str, payload: dict):
        model = self.connection["model"]
        if not model:
            raise ValueError("Choisissez un modèle dans la connexion LLM.")
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
        if self.protocol == "ollama":
            response = self.request("POST", "/api/chat", {"model": model, "messages": messages,
                "stream": False, "think": False, "format": "json", "keep_alive": 0,
                "options": {"num_ctx": 8192, "num_predict": 1200, "temperature": 0}})
            if not response.get("done") or response.get("done_reason") == "length":
                raise ValueError("La génération a été interrompue. Réduisez le nombre de messages.")
            message = response.get("message")
            if not isinstance(message, dict):
                raise ValueError("La réponse du serveur LLM est invalide.")
            content = message.get("content", "")
        else:
            body = {"model": model, "messages": messages, "temperature": 0, "max_tokens": 1200, "stream": False}
            if self.protocol == "omlx":
                body["chat_template_kwargs"] = {"enable_thinking": False}
            response = self.request("POST", "/chat/completions", body)
            choices = response.get("choices", [])
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict) or choices[0].get("finish_reason") != "stop":
                raise ValueError("La génération a été interrompue ou tronquée. Essayez un autre modèle.")
            message = choices[0].get("message")
            if not isinstance(message, dict):
                raise ValueError("La réponse du serveur LLM est invalide.")
            content = message.get("content", "")
        if not isinstance(content, str):
            raise ValueError("Le serveur LLM n’a pas renvoyé de texte.")
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content).strip()
        try:
            result = json.loads(content)
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except (ValueError, TypeError):
            raise ValueError("Le modèle n’a pas produit le JSON attendu. Essayez un autre modèle.") from None
