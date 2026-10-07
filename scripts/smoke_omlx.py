"""Real local generation through the application; synthetic mail, temporary data."""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:11435/v1")
    parser.add_argument("--model", default="Qwen3-8B-4bit")
    parser.add_argument("--output", default=str(Path(tempfile.gettempdir()) / "mailaya-omlx-proof.json"))
    args = parser.parse_args()
    from fastapi.testclient import TestClient
    from app.auth import SecretStore, UserAuth
    from app.classifier import DemoClassifier
    from app.db import Database
    from app.runner import RunManager
    with tempfile.TemporaryDirectory(prefix="mailaya-omlx-") as directory:
        data = Path(directory)
        # Set the data location before app import so initialization never opens
        # the user's real database. These variables affect this script only.
        os.environ["LAYA_MAIL_DATA_DIR"] = directory
        os.environ["LAYA_BACKEND"] = "demo"
        os.environ["MAILAYA_SECURE_COOKIES"] = "false"
        import app.main as app
        app.settings = replace(app.settings, data_dir=data, database_path=data / "mail.sqlite3")
        app.database = Database(app.settings.database_path)
        app.user_auth = UserAuth(app.database)
        app.secrets_store = SecretStore(data / "imap.key")
        app.classifier = DemoClassifier()
        app.runner = RunManager(app.database, app.classifier, {})
        with TestClient(app.app, headers={"X-Mailaya-Request": "1"}) as client:
            def checked(response, status=200):
                if response.status_code != status:
                    raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")
                return response.json()
            checked(client.post("/api/users", json={"username": "omlx-smoke", "password": "synthetic-smoke-password-123"}), 201)
            model_list = checked(client.post("/api/workspace/connections/discover", json={"base_url": args.url}))["models"]
            if args.model not in model_list:
                raise RuntimeError("Le modèle demandé n’est pas dans le catalogue réel.")
            connection = checked(client.post("/api/workspace/connections", json={"name": "oMLX smoke", "base_url": args.url, "model": args.model}), 201)["id"]
            checked(client.put("/api/workspace/accounts/0/options", json={"brief_enabled": True, "llm_enabled": True,
                "natural_search_enabled": True, "connection_id": connection}))
            # Stable synthetic sources make source validation measurable, without loading PyTorch.
            user = client.get("/api/session").json()["user"]["id"]
            run = app.database.create_run("demo", "2026-10-01", 3, "demonstration", user)
            now = datetime.now(timezone.utc).isoformat()
            app.database.add_messages(run, [
                {"graph_id": "synthetic-devis", "sender_name": "Camille", "sender_address": "camille@example.test",
                 "subject": "Devis à valider", "body_preview": "Merci de valider le devis avant vendredi. Une réponse est attendue.", "received_at": now},
                {"graph_id": "synthetic-reunion", "sender_name": "Alex", "sender_address": "alex@example.test",
                 "subject": "Réunion projet", "body_preview": "Merci de confirmer votre présence à la réunion demain.", "received_at": now},
                {"graph_id": "synthetic-newsletter", "sender_name": "Veille", "sender_address": "veille@example.test",
                 "subject": "Newsletter de la semaine", "body_preview": "Les actualités hebdomadaires. Aucune réponse nécessaire.", "received_at": now},
            ])
            emails = app.database.emails_for_run(run)
            for email in emails:
                request = email["graph_id"] != "synthetic-newsletter"
                app.database.complete_email(email["id"], {"category": "Demande" if request else "Newsletter", "category_scores": {"Demande": .9 if request else .1},
                    "priority_score": 85 if request else 10, "spam_score": 2, "action_score": 90 if request else 5, "duration_ms": 1})
            app.database.set_run(run, status="complete", finished_at=now)
            started = time.monotonic()
            brief = checked(client.post("/api/workspace/brief", json={"refresh": True}))
            brief_seconds = time.monotonic() - started
            if not brief["insights"] or not all(i["email_id"] in {e["id"] for e in emails} for i in brief["insights"]):
                raise RuntimeError("Le brief réel ne contient pas de sources valides.")
            print(f"Brief oMLX réel : {len(brief['insights'])} résumés sourcés en {brief_seconds:.2f} s.", flush=True)
            started = time.monotonic()
            search = checked(client.post("/api/workspace/natural-search", json={"query": "Les demandes de devis encore à faire"}))
            search_seconds = time.monotonic() - started
            print("Filtres produits par oMLX : " + json.dumps(search["filters"], ensure_ascii=False), flush=True)
            if not search["emails"] or not any(e["graph_id"] == "synthetic-devis" for e in search["emails"]):
                raise RuntimeError("La recherche réelle ne retrouve pas le devis synthétique.")
            print(f"Recherche oMLX réelle : {search['total']} résultat(s) en {search_seconds:.2f} s.", flush=True)
            proof = {"verified_at": now, "model": args.model, "base_url": args.url, "catalogue_size": len(model_list),
                     "brief_seconds": round(brief_seconds, 2), "search_seconds": round(search_seconds, 2),
                     "brief": brief, "search": search, "data": "synthetic only", "classifier": "synthetic stored predictions, not real LAYA/Julia weights"}
            Path(args.output).write_text(json.dumps(proof, ensure_ascii=False, indent=2))
            print("Preuve enregistrée : " + args.output)


if __name__ == "__main__":
    main()
