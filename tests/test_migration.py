import sqlite3
from app.auth import UserAuth
from app.db import Database


def test_single_user_database_is_preserved_but_not_assigned_to_new_users(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL,
                since_date TEXT NOT NULL, requested_limit INTEGER NOT NULL, status TEXT NOT NULL,
                total INTEGER DEFAULT 0, processed INTEGER DEFAULT 0, failed INTEGER DEFAULT 0,
                error TEXT, model_backend TEXT, created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT);
            CREATE TABLE emails (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER REFERENCES runs(id) ON DELETE CASCADE,
                graph_id TEXT, sender_name TEXT, sender_address TEXT, subject TEXT, body_preview TEXT,
                received_at TEXT, status TEXT DEFAULT 'pending', category TEXT, category_scores TEXT,
                priority_score REAL, spam_score REAL, action_score REAL, duration_ms REAL, error TEXT, UNIQUE(run_id, graph_id));
            INSERT INTO runs (source, since_date, requested_limit, status, created_at) VALUES ('legacy', '2026-09-01', 1, 'complete', '2026-09-01');
            INSERT INTO emails (run_id, graph_id, subject) VALUES (1, 'old', 'private subject');
        """)
    db = Database(path)
    db = Database(path)  # Initialization is idempotent.
    user = UserAuth(db).register("alice", "test-password-12345")
    assert db.get_run(1)["user_id"] is None
    assert db.latest_run(user["id"]) is None
    assert db.latest_run() is None
    assert db.get_run(1, user["id"]) is None
    assert db.emails_for_run(1)[0]["subject"] == "private subject"
    db.clear(user["id"])
    db.clear()
    assert db.get_run(1) is not None
