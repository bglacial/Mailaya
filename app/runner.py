from __future__ import annotations

import statistics
import threading
import time
from datetime import datetime
from typing import Any

from .classifier import Classifier, ClassifierLoadError
from .db import Database, utc_now
from .demo_data import demo_messages
from .inference import InferenceCancelled


ACTIVE_STATUSES = {"queued", "fetching", "running"}


class RunManager:
    def __init__(self, db: Database, classifier: Classifier, providers: dict[str, Any], provider_factory=None,
                 classifiers: dict[str, Classifier] | None = None):
        self.db = db
        self.classifier = classifier
        self.classifiers = {classifier.name: classifier, **(classifiers or {})}
        self.providers = providers
        self.provider_factory = provider_factory
        self._lock = threading.RLock()
        self._classifier_lock = threading.Lock()
        self._threads: dict[int, threading.Thread] = {}
        self._active_inference: tuple[int, Classifier] | None = None
        self._stopping = False

    def start(self, source: str, since: str, limit: int, user_id: int | None = None,
              imap_account_id: int | None = None, model_backend: str | None = None,
              incremental: bool = False) -> int:
        with self._lock:
            if self._stopping:
                raise RuntimeError("Le service est en cours d’arrêt. Réessayez après son redémarrage.")
            if self.db.active_run(user_id):
                raise RuntimeError("Une exécution est déjà en cours pour votre compte.")
            selected = self.classifiers.get(model_backend or self.classifier.name)
            if selected is None:
                raise RuntimeError("Ce modèle n’est pas disponible. Choisissez LAYA ou Julia.")
            run_id = self.db.create_run(source, since, limit, selected.name, user_id, imap_account_id, selected.model)
            with self.db.connect() as connection:
                connection.execute("UPDATE runs SET incremental=? WHERE id=?", (int(incremental), run_id))
            self._launch(run_id)
            return run_id

    def _launch(self, run_id: int) -> None:
        with self._lock:
            if self._stopping:
                return
            current = self._threads.get(run_id)
            if current and current.is_alive():
                return
            thread = threading.Thread(target=self._execute, args=(run_id,), daemon=True, name=f"laya-run-{run_id}")
            self._threads[run_id] = thread
            thread.start()

    def _execute(self, run_id: int) -> None:
        try:
            with self._lock:
                run = self.db.get_run(run_id)
                if self._stopping or not run or run["status"] == "paused":
                    return
                classifier = self.classifiers.get(run["model_backend"])
                if classifier is None:
                    raise ClassifierLoadError("Le modèle de cette exécution n’est plus disponible. Lancez une nouvelle analyse.")
                if not run["started_at"]:
                    self.db.set_run(run_id, status="fetching", started_at=utc_now(), error=None)
            if run["total"] == 0:
                if run["source"] == "demo":
                    messages = demo_messages(run["since_date"], run["requested_limit"])
                else:
                    provider = self.provider_factory(run) if self.provider_factory else self.providers.get(run["source"])
                    if provider is None:
                        raise RuntimeError(f"La source {run['source']} n'est pas disponible.")
                    messages = provider.fetch_messages(run["since_date"], run["requested_limit"])
                self.db.add_messages(run_id, messages)
                if not messages:
                    self.db.set_run(run_id, status="empty", finished_at=utc_now())
                    return
            with self._classifier_lock:
                with self._lock:
                    current = self.db.get_run(run_id)
                    if self._stopping or not current or current["status"] == "paused":
                        return
                    self.db.set_run(run_id, status="running")
                    begin = getattr(classifier, "begin_run", None)
                    if begin:
                        begin()
                    self._active_inference = (run_id, classifier)
                try:
                    while True:
                        run = self.db.get_run(run_id)
                        if self._stopping or not run or run["status"] == "paused":
                            return
                        email = self.db.next_pending_email(run_id)
                        if not email:
                            break
                        try:
                            self.db.complete_email(email["id"], classifier.classify(email))
                        except InferenceCancelled:
                            return
                        except ClassifierLoadError:
                            raise
                        except Exception as exc:
                            self.db.fail_email(email["id"], str(exc))
                finally:
                    # Reap the process before marking completion or allowing another batch.
                    try:
                        classifier.unload()
                    finally:
                        with self._lock:
                            self._active_inference = None
                with self._lock:
                    final = self.db.get_run(run_id)
                    if final and final["status"] != "paused":
                        status = "complete" if final["total"] else "empty"
                        self.db.set_run(run_id, status=status, finished_at=utc_now())
        except Exception as exc:
            self.db.set_run(run_id, status="failed", error=str(exc)[:800], finished_at=utc_now())
        finally:
            with self._lock:
                self._threads.pop(run_id, None)
                current = self.db.get_run(run_id)
                # Resume can arrive after a worker decided to pause, but before it exits.
                if not self._stopping and current and current["status"] == "running":
                    self._launch(run_id)

    def pause(self, run_id: int) -> None:
        with self._lock:
            run = self.db.get_run(run_id)
            if not run or run["status"] not in ACTIVE_STATUSES:
                raise RuntimeError("Cette exécution ne peut pas être mise en pause.")
            self.db.set_run(run_id, status="paused")
            if self._active_inference and self._active_inference[0] == run_id:
                cancel = getattr(self._active_inference[1], "cancel", None)
                if cancel:
                    cancel()

    def resume(self, run_id: int) -> None:
        with self._lock:
            if self._stopping:
                raise RuntimeError("Le service est en cours d’arrêt. Réessayez après son redémarrage.")
            run = self.db.get_run(run_id)
            if not run or run["status"] != "paused":
                raise RuntimeError("Cette exécution n'est pas en pause.")
            if self.db.active_run(run["user_id"]):
                raise RuntimeError("Une autre exécution est déjà en cours pour votre compte.")
            self.db.set_run(run_id, status="running")
            self._launch(run_id)

    def clear(self, user_id: int | None) -> None:
        with self._lock:
            if self.db.active_run(user_id):
                raise RuntimeError("Mettez l’exécution en pause avant d’effacer les résultats.")
            for run_id, thread in self._threads.items():
                run = self.db.get_run(run_id)
                if thread.is_alive() and run and run["user_id"] == user_id:
                    raise RuntimeError("La mise en pause est en cours. Réessayez dans quelques secondes.")
            self.db.clear(user_id)

    def shutdown(self) -> None:
        with self._lock:
            self._stopping = True
            threads = list(self._threads.values())
            for run_id in self._threads:
                run = self.db.get_run(run_id)
                if run and run["status"] in ACTIVE_STATUSES:
                    self.db.set_run(run_id, status="paused")
            if self._active_inference:
                cancel = getattr(self._active_inference[1], "cancel", None)
                if cancel:
                    cancel()
        deadline = time.monotonic() + 6
        for thread in threads:
            thread.join(timeout=max(0, deadline - time.monotonic()))

    def dashboard(self, user_id: int | None = None) -> dict[str, Any]:
        run = self.db.latest_run(user_id)
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
