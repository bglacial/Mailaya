from __future__ import annotations

import statistics
import threading
from datetime import datetime
from typing import Any

from .classifier import Classifier
from .db import Database, utc_now
from .demo_data import demo_messages


ACTIVE_STATUSES = {"queued", "fetching", "running"}


class RunManager:
    def __init__(self, db: Database, classifier: Classifier, providers: dict[str, Any]):
        self.db = db
        self.classifier = classifier
        self.providers = providers
        self._lock = threading.Lock()
        self._threads: dict[int, threading.Thread] = {}

    def start(self, source: str, since: str, limit: int) -> int:
        latest = self.db.latest_run()
        if latest and latest["status"] in ACTIVE_STATUSES:
            raise RuntimeError("Une exécution est déjà en cours.")
        run_id = self.db.create_run(source, since, limit, self.classifier.name)
        self._launch(run_id)
        return run_id

    def _launch(self, run_id: int) -> None:
        with self._lock:
            current = self._threads.get(run_id)
            if current and current.is_alive():
                return
            thread = threading.Thread(target=self._execute, args=(run_id,), daemon=True, name=f"laya-run-{run_id}")
            self._threads[run_id] = thread
            thread.start()

    def _execute(self, run_id: int) -> None:
        try:
            run = self.db.get_run(run_id)
            if not run:
                return
            if not run["started_at"]:
                self.db.set_run(run_id, status="fetching", started_at=utc_now(), error=None)
            if run["total"] == 0:
                if run["source"] == "demo":
                    messages = demo_messages(run["since_date"], run["requested_limit"])
                else:
                    provider = self.providers.get(run["source"])
                    if provider is None:
                        raise RuntimeError(f"La source {run['source']} n'est pas disponible.")
                    messages = provider.fetch_messages(run["since_date"], run["requested_limit"])
                self.db.add_messages(run_id, messages)
            self.db.set_run(run_id, status="running")

            while True:
                run = self.db.get_run(run_id)
                if not run or run["status"] == "paused":
                    return
                email = self.db.next_pending_email(run_id)
                if not email:
                    break
                try:
                    self.db.complete_email(email["id"], self.classifier.classify(email))
                except Exception as exc:  # Keep the batch running when one message is malformed.
                    self.db.fail_email(email["id"], str(exc))

            final = self.db.get_run(run_id)
            status = "complete" if final and final["total"] else "empty"
            self.db.set_run(run_id, status=status, finished_at=utc_now())
        except Exception as exc:
            self.db.set_run(run_id, status="failed", error=str(exc)[:800], finished_at=utc_now())

    def pause(self, run_id: int) -> None:
        run = self.db.get_run(run_id)
        if not run or run["status"] not in ACTIVE_STATUSES:
            raise RuntimeError("Cette exécution ne peut pas être mise en pause.")
        self.db.set_run(run_id, status="paused")

    def resume(self, run_id: int) -> None:
        run = self.db.get_run(run_id)
        if not run or run["status"] != "paused":
            raise RuntimeError("Cette exécution n'est pas en pause.")
        self.db.set_run(run_id, status="running")
        self._launch(run_id)

    def dashboard(self) -> dict[str, Any]:
        run = self.db.latest_run()
        if not run:
            return {"run": None, "emails": [], "metrics": self._metrics(None, [])}
        emails = self.db.emails_for_run(run["id"])
        return {"run": run, "emails": emails, "metrics": self._metrics(run, emails)}

    @staticmethod
    def _metrics(run: dict[str, Any] | None, emails: list[dict[str, Any]]) -> dict[str, Any]:
        durations = [float(item["duration_ms"]) for item in emails if item["duration_ms"] is not None]
        elapsed = 0.0
        if run and run.get("started_at"):
            end = run.get("finished_at") or utc_now()
            elapsed = max(0.0, (datetime.fromisoformat(end) - datetime.fromisoformat(run["started_at"])).total_seconds())
        p95 = 0.0
        if durations:
            ordered = sorted(durations)
            p95 = ordered[min(len(ordered) - 1, max(0, round(0.95 * len(ordered) - 1)))]
        categories: dict[str, int] = {}
        for email in emails:
            if email.get("category"):
                categories[email["category"]] = categories.get(email["category"], 0) + 1
        processed = run["processed"] if run else 0
        return {
            "elapsed_seconds": round(elapsed, 1),
            "average_ms": round(statistics.fmean(durations), 1) if durations else 0.0,
            "p95_ms": round(p95, 1),
            "per_second": round(processed / elapsed, 1) if elapsed else 0.0,
            "categories": categories,
        }
