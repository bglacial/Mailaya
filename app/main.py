from __future__ import annotations

from dataclasses import replace
from contextlib import asynccontextmanager
from datetime import date
import html
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, SecretStr, field_validator

from .auth import SESSION_COOKIE, SESSION_SECONDS, SecretStore, UserAuth
from .inference import build_process_classifier
from .config import JULIA_MODEL, JULIA_REVISION, LAYA_MODEL, get_settings
from .db import Database
from .imap import ImapMailClient
from .runner import RunManager


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9@._+\-]+$")
    password: SecretStr = Field(min_length=12, max_length=256)


class PasswordChange(BaseModel):
    current_password: SecretStr = Field(min_length=1, max_length=256)
    new_password: SecretStr = Field(min_length=12, max_length=256)


class ImapAccountRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    host: str = Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9.\-]+$")
    port: int = Field(default=993, ge=1, le=65535)
    security: Literal["ssl", "starttls"] = "ssl"
    username: str = Field(min_length=1, max_length=320)
    password: SecretStr | None = Field(default=None, max_length=1024)
    mailbox: str = Field(default="INBOX", min_length=1, max_length=255)

    @field_validator("name", "host", "username", "mailbox")
    @classmethod
    def clean_text(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Ce champ doit contenir du texte sans caractère de contrôle.")
        return value


class RunRequest(BaseModel):
    source: Literal["demo", "imap"] = "demo"
    since_date: date
    limit: int = Field(default=100, ge=1, le=5000)
    imap_account_id: int | None = Field(default=None, ge=1)
    model: Literal["laya", "julia"] | None = None


settings = get_settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.data_dir.chmod(0o700)
database = Database(settings.database_path)
user_auth = UserAuth(database)
secrets_store = SecretStore(settings.data_dir / "imap.key")


def provider_for(run: dict):
    account = runner.db.imap_account(run["imap_account_id"], run["user_id"])
    if not account:
        raise RuntimeError("Ce compte IMAP n’est plus disponible. Choisissez un autre compte.")
    return ImapMailClient(account, secrets_store.decrypt(account["password_encrypted"]))


classifier = build_process_classifier(settings)
runner = RunManager(database, classifier, {}, provider_factory=provider_for,
                    classifiers={"laya-pytorch": build_process_classifier(replace(settings, laya_model=LAYA_MODEL), "laya"),
                                 "julia-pytorch": build_process_classifier(replace(settings, julia_model=JULIA_MODEL, julia_revision=JULIA_REVISION), "julia")})


@asynccontextmanager
async def lifespan(app):
    try:
        yield
    finally:
        runner.shutdown()


app = FastAPI(title="Mailaya", version="0.3.1", docs_url="/api/docs", redoc_url=None, lifespan=lifespan)
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.middleware("http")
async def protect_requests(request: Request, call_next):
    route_path = request.scope["path"].removeprefix(request.scope.get("root_path", ""))
    if route_path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        # A custom header cannot be submitted by a cross-site HTML form; no CORS is enabled.
        origin = request.headers.get("origin")
        if request.headers.get("x-mailaya-request") != "1" or (
            origin and (urlsplit(origin).scheme, urlsplit(origin).netloc) != (request.url.scheme, request.url.netloc)
        ):
            return JSONResponse(status_code=403, content={"detail": "La demande de sécurité est invalide. Rechargez la page."})
    response = await call_next(request)
    if route_path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    # Pydantic's default validation response includes the submitted value, including passwords.
    return JSONResponse(status_code=422, content={"detail": "Certains champs sont invalides. Vérifiez les valeurs et la longueur du mot de passe."})


def optional_user(request: Request) -> dict | None:
    token = request.cookies.get(SESSION_COOKIE)
    user = user_auth.user_for_session(token)
    if token and not user:
        raise HTTPException(401, "Votre session a expiré. Connectez-vous à nouveau.")
    return user


def current_user(request: Request) -> dict:
    user = optional_user(request)
    if not user:
        raise HTTPException(401, "Connectez-vous pour accéder à vos comptes et à vos messages.")
    return user


User = Annotated[dict, Depends(current_user)]
Visitor = Annotated[dict | None, Depends(optional_user)]


def set_session(request: Request, response: Response, user: dict):
    user_auth.logout(request.cookies.get(SESSION_COOKIE))
    response.set_cookie(SESSION_COOKIE, user_auth.create_session(user["id"]), max_age=SESSION_SECONDS,
                        path=request.scope.get("root_path") or "/", httponly=True, samesite="lax",
                        secure=settings.secure_cookies or request.url.scheme == "https")


@app.get("/", include_in_schema=False)
def index(request: Request) -> HTMLResponse:
    root = html.escape(request.scope.get("root_path", "").rstrip("/"), quote=True)
    return HTMLResponse((static_dir / "index.html").read_text().replace("__MAILAYA_ROOT__", root))


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "backend": classifier.name, "model": classifier.model,
            "apple_silicon": settings.is_apple_silicon}


@app.get("/api/session")
def session(request: Request) -> dict:
    return {"user": user_auth.user_for_session(request.cookies.get(SESSION_COOKIE))}


@app.post("/api/users", status_code=201)
def register(body: Credentials, request: Request, response: Response) -> dict:
    try:
        user = user_auth.register(body.username, body.password.get_secret_value())
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    set_session(request, response, user)
    return {"user": user}


@app.post("/api/login")
def login(body: Credentials, request: Request, response: Response) -> dict:
    user = user_auth.login(body.username, body.password.get_secret_value())
    if not user:
        raise HTTPException(401, "Identifiant ou mot de passe incorrect. Réessayez.")
    set_session(request, response, user)
    return {"user": user}


@app.post("/api/logout", status_code=204)
def logout(request: Request, response: Response) -> None:
    user_auth.logout(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path=request.scope.get("root_path") or "/")


@app.put("/api/password")
def change_password(body: PasswordChange, user: User, request: Request, response: Response) -> dict:
    if not user_auth.login(user["username"], body.current_password.get_secret_value()):
        raise HTTPException(401, "Le mot de passe actuel est incorrect.")
    user_auth.change_password(user["id"], body.new_password.get_secret_value())
    set_session(request, response, user)
    return {"user": user}


@app.get("/api/dashboard")
def dashboard(user: Visitor) -> dict:
    payload = runner.dashboard(user["id"] if user else None)
    payload["imap_accounts"] = runner.db.imap_accounts(user["id"]) if user else []
    effective = runner.classifiers.get(payload["run"]["model_backend"], classifier) if payload["run"] else classifier
    payload["configuration"] = {
        "backend": effective.name, "model": effective.model, "max_emails": settings.max_emails_per_run,
        "default_model": "laya" if classifier.name == "laya-pytorch" else "julia",
        "models": [{"id": "laya", "name": "LAYA multilingual", "model": LAYA_MODEL},
                   {"id": "julia", "name": "Julia-1", "model": JULIA_MODEL}],
    }
    return payload


def owned_run(run_id: int, user: dict | None) -> dict:
    run = runner.db.get_run(run_id, user["id"]) if user else runner.db.get_run(run_id)
    if not run or (not user and (run["user_id"] is not None or run["source"] != "demo")):
        raise HTTPException(404, "Cette exécution est introuvable.")
    return run


@app.post("/api/runs", status_code=202)
def start_run(body: RunRequest, user: Visitor) -> dict:
    if body.limit > settings.max_emails_per_run:
        raise HTTPException(400, f"La limite maximale configurée est {settings.max_emails_per_run} messages.")
    if body.source == "imap":
        if not user:
            raise HTTPException(401, "Connectez-vous pour configurer et analyser un compte IMAP.")
        if body.imap_account_id is None:
            raise HTTPException(400, "Choisissez un compte IMAP avant de lancer l’analyse.")
        owned_account(body.imap_account_id, user)
    elif body.imap_account_id is not None:
        raise HTTPException(400, "Le compte IMAP ne peut être utilisé qu’avec la source IMAP.")
    try:
        with runner._lock:
            if body.source == "imap":
                owned_account(body.imap_account_id, user)
            run_id = runner.start(body.source, body.since_date.isoformat(), body.limit,
                                  user["id"] if user else None, body.imap_account_id,
                                  f"{body.model}-pytorch" if body.model else None)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"run_id": run_id, "status": "queued"}


@app.post("/api/runs/{run_id}/pause")
def pause_run(run_id: int, user: Visitor) -> dict:
    owned_run(run_id, user)
    try:
        runner.pause(run_id)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"status": "paused"}


@app.post("/api/runs/{run_id}/resume")
def resume_run(run_id: int, user: Visitor) -> dict:
    owned_run(run_id, user)
    try:
        runner.resume(run_id)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"status": "running"}


@app.delete("/api/results", status_code=204)
def clear_results(user: Visitor) -> None:
    try:
        runner.clear(user["id"] if user else None)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/imap/accounts")
def list_imap_accounts(user: User) -> dict:
    return {"accounts": runner.db.imap_accounts(user["id"])}


def owned_account(account_id: int, user: dict) -> dict:
    account = runner.db.imap_account(account_id, user["id"])
    if not account:
        raise HTTPException(404, "Ce compte IMAP est introuvable.")
    return account


def save_account(body: ImapAccountRequest, user: dict, account_id: int | None = None) -> dict:
    # Serializes account changes against run creation, so a selected account cannot disappear.
    with runner._lock:
        existing = owned_account(account_id, user) if account_id is not None else None
        if existing and runner.db.account_in_use(account_id, user["id"]):
            raise HTTPException(409, "Terminez l’analyse ou effacez ses résultats avant de modifier ce compte.")
        password = body.password.get_secret_value() if body.password else ""
        if not password and not existing:
            raise HTTPException(400, "Saisissez le mot de passe ou le mot de passe d’application du compte IMAP.")
        values = body.model_dump(exclude={"password"})
        values["password_encrypted"] = secrets_store.encrypt(password) if password else existing["password_encrypted"]
        saved_id = runner.db.save_imap_account(user["id"], values, account_id)
        return next(account for account in runner.db.imap_accounts(user["id"]) if account["id"] == saved_id)


@app.post("/api/imap/accounts", status_code=201)
def add_imap_account(body: ImapAccountRequest, user: User) -> dict:
    return {"account": save_account(body, user)}


@app.put("/api/imap/accounts/{account_id}")
def update_imap_account(account_id: int, body: ImapAccountRequest, user: User) -> dict:
    return {"account": save_account(body, user, account_id)}


@app.post("/api/imap/accounts/{account_id}/test")
def test_imap_account(account_id: int, user: User) -> dict:
    account = owned_account(account_id, user)
    try:
        ImapMailClient(account, secrets_store.decrypt(account["password_encrypted"])).test_connection()
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": "connected"}


@app.delete("/api/imap/accounts/{account_id}", status_code=204)
def delete_imap_account(account_id: int, user: User) -> None:
    with runner._lock:
        owned_account(account_id, user)
        if runner.db.account_in_use(account_id, user["id"]):
            raise HTTPException(409, "Terminez l’analyse ou effacez ses résultats avant de supprimer ce compte.")
        runner.db.delete_imap_account(account_id, user["id"])
