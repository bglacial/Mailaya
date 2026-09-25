from __future__ import annotations

import hashlib
import importlib.util
import math
import re
import threading
import time
from typing import Any, Protocol

from .config import Settings


CATEGORIES = {
    "Travail": "collaboration, projet, réunion, client, équipe, recrutement",
    "Finance": "factures, paiements, abonnements, banque, remboursements",
    "Support": "incidents, assistance, sécurité, compte, renouvellement",
    "Achats": "commandes, devis, livraisons, colis et fournisseurs",
    "Événements": "invitations, conférences, formations et rencontres",
    "Social": "réseaux sociaux, communauté et notifications de plateformes",
    "Personnel": "famille, amis, rendez-vous et messages privés",
    "Marketing": "lettres d'information, promotions et campagnes commerciales",
    "Autre": "message ne correspondant clairement à aucune autre catégorie",
}

QUESTIONS = {
    "category": {
        "type": "choice",
        "instructions": "Classe cet e-mail dans la catégorie la plus utile pour organiser une boîte de réception.",
        "criteria": CATEGORIES,
    },
    "priority": {
        "type": "score",
        "instructions": "Évalue la priorité pratique de cet e-mail pour son destinataire.",
        "criteria": [
            "faible : peut être ignoré ou lu plus tard",
            "normale : information utile sans échéance proche",
            "haute : mérite une attention rapide ou contient une échéance",
            "critique : blocage, risque ou échéance immédiate",
        ],
    },
    "spam": {
        "type": "noul",
        "instructions": "Cet e-mail est-il probablement indésirable, trompeur ou non sollicité ?",
    },
    "action": {
        "type": "noul",
        "instructions": "Le destinataire doit-il répondre, décider, confirmer ou effectuer une action concrète ?",
    },
}


class Classifier(Protocol):
    name: str

    def classify(self, email: dict[str, Any]) -> dict[str, Any]: ...


def _clamp_probability(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(max(0.0, min(1.0, number)), 4)


def _extract_noul(answer: Any) -> float:
    if isinstance(answer, dict):
        for key in ("noul", "probability", "true", "score"):
            if key in answer:
                return _clamp_probability(answer[key])
    return _clamp_probability(answer)


def _extract_score(answer: Any, levels: int = 4) -> float:
    raw = answer.get("score", 0) if isinstance(answer, dict) else answer
    try:
        return round(max(0.0, min(100.0, float(raw) / (levels - 1) * 100)), 1)
    except (TypeError, ValueError):
        return 0.0


def _extract_choice(answer: Any) -> tuple[str, dict[str, float]]:
    if isinstance(answer, str):
        return answer, {answer: 1.0}
    if not isinstance(answer, dict):
        return "Autre", {"Autre": 1.0}
    choice = str(answer.get("choice") or answer.get("label") or "Autre")
    raw_scores = answer.get("probabilities") or answer.get("scores") or answer.get("distribution") or {}
    scores = {str(key): _clamp_probability(value) for key, value in raw_scores.items()} if isinstance(raw_scores, dict) else {}
    if not scores:
        scores = {choice: _clamp_probability(answer.get("confidence", 1.0))}
    return choice, scores


class LayaClassifier:
    name = "laya-mlx"

    def __init__(self, settings: Settings):
        self.settings = settings
        self._agent: Any = None
        self._load_lock = threading.Lock()

    def _load(self) -> Any:
        if self._agent is not None:
            return self._agent
        with self._load_lock:
            if self._agent is None:
                import laya_mlx as laya

                self._agent = laya.load(
                    self.settings.laya_model,
                    dtype=self.settings.laya_dtype,
                    batch_size=16,
                    compile=True,
                    pad_to_multiple=16,
                    cache_prompts=True,
                )
        return self._agent

    def classify(self, email: dict[str, Any]) -> dict[str, Any]:
        state = {
            "expéditeur": f"{email['sender_name']} <{email['sender_address']}>",
            "objet": email["subject"],
            "contenu": email["body_preview"],
        }
        agent = self._load()
        started = time.perf_counter()
        prediction = agent.predict(state, QUESTIONS)
        duration_ms = (time.perf_counter() - started) * 1000
        answers = prediction.get("answers", {})
        category, category_scores = _extract_choice(answers.get("category", {}))
        return {
            "category": category,
            "category_scores": category_scores,
            "priority_score": _extract_score(answers.get("priority", {})),
            "spam_score": round(_extract_noul(answers.get("spam", {})) * 100, 1),
            "action_score": round(_extract_noul(answers.get("action", {})) * 100, 1),
            "duration_ms": round(duration_ms, 1),
        }


class DemoClassifier:
    name = "demonstration"

    _category_keywords = {
        "Finance": ("facture", "paiement", "prélèvement", "€", "rembourse"),
        "Support": ("sécurité", "vulnerability", "incident", "domaine", "expiration"),
        "Achats": ("colis", "livraison", "devis", "commande", "fournisseur"),
        "Événements": ("rencontre", "formation", "présence", "invitation", "conférence"),
        "Social": ("réagi", "publication", "linkedin", "interaction"),
        "Marketing": ("nouveautés", "promotion", "offre", "newsletter", "gagné"),
        "Travail": ("projet", "client", "équipe", "validation", "créneau"),
        "Personnel": ("dimanche", "famille", "maman", "dîner"),
    }

    def classify(self, email: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        text = f"{email['sender_name']} {email['subject']} {email['body_preview']}".lower()
        raw: dict[str, float] = {}
        for category, keywords in self._category_keywords.items():
            raw[category] = 0.15 + sum(1.0 for keyword in keywords if keyword in text)
        raw["Autre"] = 0.2
        total = sum(math.exp(value) for value in raw.values())
        scores = {key: round(math.exp(value) / total, 4) for key, value in raw.items()}
        category = max(scores, key=scores.get)

        urgent = len(re.findall(r"urgent|avant|échéance|expire|critique|high severity|demain", text))
        action = len(re.findall(r"merci|pouvez-vous|confirmer|valider|répondre|téléchargez|update|effectu", text))
        spam = len(re.findall(r"gagné|cliquez maintenant|offre exclusive|gratuit|!!!|promo", text))
        digest = int(hashlib.sha256(email["graph_id"].encode()).hexdigest()[:4], 16)
        time.sleep(0.025 + digest % 20 / 1000)
        return {
            "category": category,
            "category_scores": scores,
            "priority_score": round(min(100, 27 + urgent * 22 + action * 8), 1),
            "spam_score": round(min(99, 4 + spam * 27 + (digest % 7)), 1),
            "action_score": round(min(99, 8 + action * 24 + urgent * 8), 1),
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        }


def build_classifier(settings: Settings) -> Classifier:
    wants_laya = settings.laya_backend == "laya" or (
        settings.laya_backend == "auto"
        and settings.is_apple_silicon
        and importlib.util.find_spec("laya_mlx") is not None
    )
    return LayaClassifier(settings) if wants_laya else DemoClassifier()
