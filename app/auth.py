from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from .db import Database, utc_now


SESSION_COOKIE = "mailaya_session"
SESSION_SECONDS = 7 * 24 * 60 * 60


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=1, maxmem=64 * 1024 * 1024)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, salt, _ = stored.split("$")
        return algorithm == "scrypt" and hmac.compare_digest(hash_password(password, bytes.fromhex(salt)), stored)
    except (ValueError, TypeError):
        return False


class UserAuth:
    def __init__(self, db: Database):
        self.db = db
        self._dummy_hash = hash_password(secrets.token_urlsafe(32))

    def register(self, username: str, password: str) -> dict:
        try:
            with self.db.connect() as connection:
                cursor = connection.execute(
                    "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                    (username.casefold(), hash_password(password), utc_now()),
                )
                return {"id": int(cursor.lastrowid), "username": username.casefold()}
        except sqlite3.IntegrityError as exc:
            raise ValueError("Cet identifiant est déjà utilisé. Choisissez-en un autre.") from exc

    def login(self, username: str, password: str) -> dict | None:
        with self.db.connect() as connection:
            row = connection.execute("SELECT * FROM users WHERE username = ?", (username.casefold(),)).fetchone()
        valid = verify_password(password, row["password_hash"] if row else self._dummy_hash)
        return {"id": row["id"], "username": row["username"]} if row and valid else None

    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        with self.db.connect() as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (time.time(),))
            connection.execute("INSERT INTO sessions VALUES (?, ?, ?)",
                               (hashlib.sha256(token.encode()).hexdigest(), user_id, time.time() + SESSION_SECONDS))
        return token

    def user_for_session(self, token: str | None) -> dict | None:
        if not token or len(token) > 128:
            return None
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT users.id, users.username FROM sessions JOIN users ON users.id = sessions.user_id WHERE token_hash = ? AND expires_at > ?",
                (hashlib.sha256(token.encode()).hexdigest(), time.time()),
            ).fetchone()
        return dict(row) if row else None

    def logout(self, token: str | None) -> None:
        if token:
            with self.db.connect() as connection:
                connection.execute("DELETE FROM sessions WHERE token_hash = ?", (hashlib.sha256(token.encode()).hexdigest(),))

    def change_password(self, user_id: int, password: str) -> None:
        with self.db.connect() as connection:
            connection.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(password), user_id))
            connection.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))


class SecretStore:
    """A persistent local key, separate from the encrypted account database."""

    def __init__(self, key_path: Path):
        key_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "wb") as file:
                file.write(Fernet.generate_key())
        self.cipher = Fernet(key_path.read_bytes())

    def encrypt(self, password: str) -> str:
        return self.cipher.encrypt(password.encode()).decode()

    def decrypt(self, encrypted: str) -> str:
        try:
            return self.cipher.decrypt(encrypted.encode()).decode()
        except InvalidToken as exc:
            raise RuntimeError("Le mot de passe IMAP est illisible. Enregistrez à nouveau ce compte avec son mot de passe.") from exc
