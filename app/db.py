from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS imap_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    security TEXT NOT NULL,
                    username TEXT NOT NULL,
                    password_encrypted TEXT NOT NULL,
                    mailbox TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    since_date TEXT NOT NULL,
                    requested_limit INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    total INTEGER NOT NULL DEFAULT 0,
                    processed INTEGER NOT NULL DEFAULT 0,
                    failed INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    model_backend TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                );

                CREATE TABLE IF NOT EXISTS emails (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    graph_id TEXT NOT NULL,
                    sender_name TEXT NOT NULL,
                    sender_address TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body_preview TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    category TEXT,
                    category_scores TEXT,
                    priority_score REAL,
                    spam_score REAL,
                    action_score REAL,
                    duration_ms REAL,
                    error TEXT,
                    UNIQUE(run_id, graph_id)
                );
                """
            )
            # Existing single-user results remain unowned and invisible to signed-in users.
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(runs)")}
            if "user_id" not in columns:
                connection.execute("ALTER TABLE runs ADD COLUMN user_id INTEGER REFERENCES users(id)")
            if "imap_account_id" not in columns:
                connection.execute("ALTER TABLE runs ADD COLUMN imap_account_id INTEGER REFERENCES imap_accounts(id) ON DELETE SET NULL")
            if "model" not in columns:
                connection.execute("ALTER TABLE runs ADD COLUMN model TEXT")
            connection.execute("CREATE INDEX IF NOT EXISTS runs_user ON runs(user_id, id)")
        self.path.chmod(0o600)

    def create_run(self, source: str, since_date: str, limit: int, backend: str,
                   user_id: int | None = None, imap_account_id: int | None = None,
                   model: str | None = None) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO runs
                (source, since_date, requested_limit, status, model_backend, created_at, user_id, imap_account_id, model)
                VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?)""",
                (source, since_date, limit, backend, utc_now(), user_id, imap_account_id, model),
            )
            return int(cursor.lastrowid)

    def get_run(self, run_id: int, user_id: int | None = None) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE id = ?" + (" AND user_id = ?" if user_id is not None else ""),
                (run_id, user_id) if user_id is not None else (run_id,),
            ).fetchone()
        return dict(row) if row else None

    def latest_run(self, user_id: int | None = None) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM runs" + (" WHERE user_id = ?" if user_id is not None else " WHERE user_id IS NULL AND source = 'demo'") + " ORDER BY id DESC LIMIT 1",
                (user_id,) if user_id is not None else (),
            ).fetchone()
        return dict(row) if row else None

    def active_run(self, user_id: int | None) -> bool:
        with self.connect() as connection:
            return connection.execute(
                "SELECT 1 FROM runs WHERE user_id IS ? AND status IN ('queued', 'fetching', 'running')"
                + (" AND source = 'demo'" if user_id is None else "") + " LIMIT 1",
                (user_id,),
            ).fetchone() is not None

    def set_run(self, run_id: int, **values: Any) -> None:
        if not values:
            return
        allowed = {"status", "total", "processed", "failed", "error", "started_at", "finished_at", "model_backend"}
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"Run fields not allowed: {sorted(unknown)}")
        assignments = ", ".join(f"{key} = ?" for key in values)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE runs SET {assignments} WHERE id = ?",  # noqa: S608 - fields are allow-listed
                (*values.values(), run_id),
            )

    def add_messages(self, run_id: int, messages: list[dict[str, Any]]) -> None:
        with self.connect() as connection:
            connection.executemany(
                """INSERT OR IGNORE INTO emails
                (run_id, graph_id, sender_name, sender_address, subject, body_preview, received_at)
                VALUES (:run_id, :graph_id, :sender_name, :sender_address, :subject, :body_preview, :received_at)""",
                [{**message, "run_id": run_id} for message in messages],
            )
            total = connection.execute("SELECT COUNT(*) FROM emails WHERE run_id = ?", (run_id,)).fetchone()[0]
            connection.execute("UPDATE runs SET total = ? WHERE id = ?", (total, run_id))

    def next_pending_email(self, run_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM emails WHERE run_id = ? AND status = 'pending' ORDER BY received_at DESC LIMIT 1",
                (run_id,),
            ).fetchone()
        return dict(row) if row else None

    def complete_email(self, email_id: int, result: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """UPDATE emails SET status = 'complete', category = ?, category_scores = ?,
                priority_score = ?, spam_score = ?, action_score = ?, duration_ms = ?, error = NULL
                WHERE id = ?""",
                (
                    result["category"],
                    json.dumps(result["category_scores"], ensure_ascii=False),
                    result["priority_score"],
                    result["spam_score"],
                    result["action_score"],
                    result["duration_ms"],
                    email_id,
                ),
            )
            run_id = connection.execute("SELECT run_id FROM emails WHERE id = ?", (email_id,)).fetchone()[0]
            self._refresh_counts(connection, run_id)

    def fail_email(self, email_id: int, error: str) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE emails SET status = 'failed', error = ? WHERE id = ?", (error[:500], email_id))
            run_id = connection.execute("SELECT run_id FROM emails WHERE id = ?", (email_id,)).fetchone()[0]
            self._refresh_counts(connection, run_id)

    @staticmethod
    def _refresh_counts(connection: sqlite3.Connection, run_id: int) -> None:
        counts = connection.execute(
            """SELECT
            SUM(CASE WHEN status = 'complete' THEN 1 ELSE 0 END),
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END)
            FROM emails WHERE run_id = ?""",
            (run_id,),
        ).fetchone()
        connection.execute(
            "UPDATE runs SET processed = ?, failed = ? WHERE id = ?",
            (counts[0] or 0, counts[1] or 0, run_id),
        )

    def emails_for_run(self, run_id: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM emails WHERE run_id = ? ORDER BY received_at DESC", (run_id,)
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["category_scores"] = json.loads(item["category_scores"] or "{}")
            results.append(item)
        return results

    def clear(self, user_id: int | None = None) -> None:
        with self.connect() as connection:
            if user_id is None:
                connection.execute("DELETE FROM runs WHERE user_id IS NULL AND source = 'demo'")
            else:
                connection.execute("DELETE FROM runs WHERE user_id = ?", (user_id,))

    def imap_accounts(self, user_id: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, name, host, port, security, username, mailbox, created_at FROM imap_accounts WHERE user_id = ? ORDER BY id",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def imap_account(self, account_id: int, user_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM imap_accounts WHERE id = ? AND user_id = ?", (account_id, user_id)).fetchone()
        return dict(row) if row else None

    def save_imap_account(self, user_id: int, values: dict[str, Any], account_id: int | None = None) -> int:
        fields = ("name", "host", "port", "security", "username", "password_encrypted", "mailbox")
        with self.connect() as connection:
            if account_id is None:
                cursor = connection.execute(
                    "INSERT INTO imap_accounts (user_id, name, host, port, security, username, password_encrypted, mailbox, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (user_id, *(values[field] for field in fields), utc_now()),
                )
                return int(cursor.lastrowid)
            connection.execute(
                "UPDATE imap_accounts SET name=?, host=?, port=?, security=?, username=?, password_encrypted=?, mailbox=? WHERE id=? AND user_id=?",
                (*(values[field] for field in fields), account_id, user_id),
            )
        return account_id

    def account_in_use(self, account_id: int, user_id: int) -> bool:
        with self.connect() as connection:
            return connection.execute(
                "SELECT 1 FROM runs WHERE imap_account_id=? AND user_id=? AND status IN ('queued', 'fetching', 'running', 'paused') LIMIT 1",
                (account_id, user_id),
            ).fetchone() is not None

    def delete_imap_account(self, account_id: int, user_id: int) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM imap_accounts WHERE id=? AND user_id=?", (account_id, user_id))
