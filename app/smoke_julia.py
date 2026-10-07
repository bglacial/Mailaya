"""Run real Julia inference against synthetic emails without accessing Gmail."""
from __future__ import annotations

import json
import math
import tempfile
import time
from pathlib import Path

from .classifier import CATEGORIES, JuliaClassifier
from .config import get_settings
from .db import Database
from .runner import RunManager


def main() -> None:
    classifier = JuliaClassifier(get_settings())
    with tempfile.TemporaryDirectory(prefix="mailaya-julia-") as directory:
        manager = RunManager(Database(Path(directory) / "smoke.sqlite3"), classifier, {})
        manager.start("demo", "2026-09-01", 3)
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            payload = manager.dashboard()
            if payload["run"]["status"] in {"complete", "failed", "empty"}:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("Le test Julia n'a pas terminé en 15 minutes.")
        run = payload["run"]
        if run["status"] != "complete" or run["processed"] != 3 or run["failed"]:
            raise RuntimeError(run.get("error") or str(payload["emails"]))
        for email in payload["emails"]:
            if email["category"] not in CATEGORIES or set(email["category_scores"]) != set(CATEGORIES):
                raise RuntimeError("Matrice des catégories Julia incomplète.")
            scores = email["category_scores"].values()
            if not all(math.isfinite(score) and 0 <= score <= 1 for score in scores):
                raise RuntimeError("Probabilités Julia invalides.")
            if not math.isclose(sum(scores), 1, abs_tol=0.002):
                raise RuntimeError("Probabilités Julia non normalisées.")
            if not all(math.isfinite(email[key]) and 0 <= email[key] <= 100
                       for key in ("priority_score", "spam_score", "action_score")):
                raise RuntimeError("Scores Julia invalides.")
        print(json.dumps({
            "backend": classifier.name, "model": classifier.model,
            "processed": run["processed"], "failed": run["failed"],
            "emails": [{key: email[key] for key in (
                "category", "priority_score", "spam_score", "action_score", "duration_ms",
            )} for email in payload["emails"]],
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
