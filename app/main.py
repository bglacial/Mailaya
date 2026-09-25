from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .classifier import build_classifier
from .config import get_settings
from .db import Database
from .gmail import GmailMailClient, GoogleAuth
from .runner import ACTIVE_STATUSES, RunManager


class RunRequest(BaseModel):
    source: Literal["demo", "gmail"] = "demo"
    since_date: date
    limit: int = Field(default=100, ge=1, le=5000)


settings = get_settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
database = Database(settings.database_path)
google_auth = GoogleAuth(settings)
gmail = GmailMailClient(google_auth)
classifier = build_classifier(settings)
runner = RunManager(database, classifier, {"gmail": gmail})

app = FastAPI(title="Mailaya", version="0.1.0", docs_url="/api/docs", redoc_url=None)
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "backend": classifier.name,
        "model": settings.laya_model,
        "gmail_configured": settings.gmail_configured,
        "apple_silicon": settings.is_apple_silicon,
    }


@app.get("/api/dashboard")
def dashboard(request: Request) -> dict:
    payload = runner.dashboard()
    payload["auth"] = {"gmail": google_auth.status()}
    payload["configuration"] = {
        "backend": classifier.name,
        "model": settings.laya_model,
        "max_emails": settings.max_emails_per_run,
        "gmail_redirect_uri": str(request.url_for("google_callback")),
    }
    return payload


@app.post("/api/runs", status_code=202)
def start_run(request: RunRequest) -> dict:
    if request.limit > settings.max_emails_per_run:
        raise HTTPException(400, f"La limite maximale configurée est {settings.max_emails_per_run} messages.")
    if request.source == "gmail" and google_auth.status()["state"] != "connected":
        raise HTTPException(401, "Connectez votre compte Gmail avant de lancer l'analyse.")
    try:
        run_id = runner.start(request.source, request.since_date.isoformat(), request.limit)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"run_id": run_id, "status": "queued"}


@app.post("/api/runs/{run_id}/pause")
def pause_run(run_id: int) -> dict:
    try:
        runner.pause(run_id)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"status": "paused"}


@app.post("/api/runs/{run_id}/resume")
def resume_run(run_id: int) -> dict:
    try:
        runner.resume(run_id)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"status": "running"}


@app.delete("/api/results", status_code=204)
def clear_results() -> None:
    latest = database.latest_run()
    if latest and latest["status"] in ACTIVE_STATUSES:
        raise HTTPException(409, "Mettez l'exécution en pause avant d'effacer les résultats.")
    database.clear()


@app.post("/api/auth/google/start")
def start_google_auth(request: Request) -> dict:
    redirect_uri = str(request.url_for("google_callback"))
    try:
        return {"authorization_url": google_auth.start_flow(redirect_uri)}
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/auth/google/callback", name="google_callback", include_in_schema=False)
def google_callback(code: str | None = None, state: str | None = None, error: str | None = None) -> RedirectResponse:
    if error:
        raise HTTPException(400, f"Google a refusé la connexion : {error}")
    if not code or not state:
        raise HTTPException(400, "La réponse Google est incomplète.")
    try:
        google_auth.finish_flow(state, code)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    return RedirectResponse(url="/?gmail=connected", status_code=303)


@app.delete("/api/auth/google", status_code=204)
def disconnect_google() -> None:
    google_auth.disconnect()
