"""Personal triage state. Predictions stay immutable; annotations survive new runs."""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .db import utc_now


class AccountOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sync_enabled: bool = False
    sync_minutes: int = Field(default=30, ge=5, le=1440)
    sync_limit: int = Field(default=50, ge=1, le=500)
    sync_model: Literal["laya", "julia"] = "julia"
    brief_enabled: bool = False
    brief_auto: bool = False
    brief_hour: int = Field(default=8, ge=0, le=23)
    timezone: str = Field(default="Europe/Paris", max_length=80)
    llm_enabled: bool = False
    natural_search_enabled: bool = False
    comparison_enabled: bool = False
    notifications_enabled: bool = False
    connection_id: int | None = Field(default=None, ge=1)


class MailFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: int | None = Field(default=None, ge=1)
    demo_only: bool = False
    run_id: int | None = Field(default=None, ge=1)
    q: str = Field(default="", max_length=300)
    sender: str = Field(default="", max_length=320)
    category: str = Field(default="", max_length=100)
    since: str = Field(default="", pattern=r"^(|\d{4}-\d{2}-\d{2})$")
    until: str = Field(default="", pattern=r"^(|\d{4}-\d{2}-\d{2})$")
    priority_min: float = Field(default=0, ge=0, le=100)
    spam_max: float = Field(default=100, ge=0, le=100)
    action_min: float = Field(default=0, ge=0, le=100)
    task: Literal["all", "todo", "done", "snoozed"] = "all"
    todo: bool = False
    review: bool = False
    sort: Literal["date", "priority", "action", "sender"] = "date"
    conversations: bool = False
    conversation: str = Field(default="", max_length=1000)
    offset: int = Field(default=0, ge=0, le=10000000)
    limit: int = Field(default=50, ge=1, le=200)

    @field_validator("since", "until")
    @classmethod
    def valid_date(cls, value):
        if value:
            date.fromisoformat(value)
        return value


class Annotation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str | None = Field(default=None, min_length=1, max_length=100)
    priority: float | None = Field(default=None, ge=0, le=100)
    task: Literal["todo", "done", "snoozed"] = "todo"
    snoozed_until: str | None = None


class PersonalRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    field: Literal["sender", "subject", "text"] = "sender"
    contains: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    priority: float | None = Field(default=None, ge=0, le=100)
    enabled: bool = True


def initialize(connection):
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS account_options (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            account_id INTEGER NOT NULL, options TEXT NOT NULL, runtime TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY(user_id, account_id));
        CREATE TABLE IF NOT EXISTS annotations (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            graph_id TEXT NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY(user_id, graph_id));
        CREATE TABLE IF NOT EXISTS correction_events (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            graph_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS personal_rules (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            account_id INTEGER NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS saved_views (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL, filters TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS llm_connections (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL, protocol TEXT NOT NULL, base_url TEXT NOT NULL,
            model TEXT NOT NULL, secret TEXT NOT NULL DEFAULT '', allow_remote INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS briefs (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            account_id INTEGER NOT NULL, day TEXT NOT NULL, mode TEXT NOT NULL,
            payload TEXT NOT NULL, created_at TEXT NOT NULL,
            UNIQUE(user_id, account_id, day));
        CREATE INDEX IF NOT EXISTS emails_identity ON emails(graph_id, id);
        CREATE INDEX IF NOT EXISTS emails_run_status ON emails(run_id, status);
    """)
    for table, columns in {"emails": {"thread_key": "TEXT", "message_id": "TEXT"},
                           "runs": {"incremental": "INTEGER NOT NULL DEFAULT 0", "reference_run_id": "INTEGER"}}.items():
        existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


class Workspace:
    def __init__(self, db):
        self.db = db

    def options(self, user_id, account_id=0):
        with self.db.connect() as c:
            row = c.execute("SELECT options,runtime FROM account_options WHERE user_id=? AND account_id=?",
                            (user_id, account_id)).fetchone()
        return {"options": AccountOptions(**json.loads(row["options"])).model_dump() if row else AccountOptions().model_dump(),
                "runtime": json.loads(row["runtime"]) if row else {}}

    def save_options(self, user_id, account_id, options):
        with self.db.connect() as c:
            c.execute("INSERT INTO account_options(user_id,account_id,options) VALUES (?,?,?) "
                      "ON CONFLICT(user_id,account_id) DO UPDATE SET options=excluded.options",
                      (user_id, account_id, json.dumps(options)))

    def runtime(self, user_id, account_id, **values):
        current = self.options(user_id, account_id)
        current["runtime"].update(values)
        self.save_options(user_id, account_id, current["options"])
        with self.db.connect() as c:
            c.execute("UPDATE account_options SET runtime=? WHERE user_id=? AND account_id=?",
                      (json.dumps(current["runtime"]), user_id, account_id))

    def rules(self, user_id, account_id=None):
        with self.db.connect() as c:
            rows = c.execute("SELECT * FROM personal_rules WHERE user_id=?" +
                             (" AND account_id=?" if account_id is not None else "") + " ORDER BY id",
                             (user_id, account_id) if account_id is not None else (user_id,)).fetchall()
        return [{"id": r["id"], "account_id": r["account_id"], **json.loads(r["payload"])} for r in rows]

    def add_rule(self, user_id, account_id, rule):
        with self.db.connect() as c:
            return c.execute("INSERT INTO personal_rules(user_id,account_id,payload) VALUES (?,?,?)",
                             (user_id, account_id, json.dumps(rule))).lastrowid

    def annotation(self, user_id, email_id, annotation):
        email = self.owned_email(user_id, email_id)
        if not email:
            return False
        value = json.dumps(annotation, ensure_ascii=False)
        with self.db.connect() as c:
            c.execute("INSERT INTO annotations VALUES (?,?,?,?) ON CONFLICT(user_id,graph_id) "
                      "DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
                      (user_id, email["graph_id"], value, utc_now()))
            c.execute("INSERT INTO correction_events(user_id,graph_id,payload,created_at) VALUES (?,?,?,?)",
                      (user_id, email["graph_id"], value, utc_now()))
        return True

    def owned_email(self, user_id, email_id):
        with self.db.connect() as c:
            row = c.execute("SELECT e.*,r.imap_account_id,r.model_backend,a.payload AS annotation FROM emails e JOIN runs r ON r.id=e.run_id "
                            "LEFT JOIN annotations a ON a.user_id=r.user_id AND a.graph_id=e.graph_id "
                            "WHERE e.id=? AND r.user_id=?", (email_id, user_id)).fetchone()
        return dict(row) if row else None

    def messages(self, user_id, filters: MailFilters, *, paginate=True):
        # SQL prefilters owner/scope; latest prediction per mailbox identity avoids duplicates.
        where, args = ["r.user_id=?"], [user_id]
        if filters.account_id:
            where.append("r.imap_account_id=?")
            args.append(filters.account_id)
        if filters.run_id:
            where.append("r.id=?")
            args.append(filters.run_id)
        with self.db.connect() as c:
            rows = c.execute("SELECT e.*,r.imap_account_id,r.model_backend,a.payload AS annotation "
                             "FROM emails e JOIN runs r ON r.id=e.run_id LEFT JOIN annotations a "
                             "ON a.user_id=r.user_id AND a.graph_id=e.graph_id WHERE " + " AND ".join(where) +
                             " AND e.id=(SELECT MAX(e2.id) FROM emails e2 JOIN runs r2 ON r2.id=e2.run_id "
                             "WHERE e2.graph_id=e.graph_id AND r2.user_id=r.user_id" +
                             (" AND r2.id=r.id" if filters.run_id else "") + ") ORDER BY e.received_at DESC", args).fetchall()
        rules = self.rules(user_id)
        emails = [self.decorate(dict(r), rules) for r in rows]
        results = [e for e in emails if self.matches(e, filters)]
        sort = {"date": lambda e: e["received_at"], "priority": lambda e: e["effective_priority"] or 0,
                "action": lambda e: e["action_score"] or 0, "sender": lambda e: e["sender_address"].casefold()}
        results.sort(key=sort[filters.sort], reverse=filters.sort != "sender")
        conversations = {}
        for e in results:
            conversations.setdefault(e["conversation"], []).append(e)
        if filters.conversations:
            results = [{**group[0], "conversation_count": len(group), "conversation_ids": [e["id"] for e in group]}
                       for group in conversations.values()]
        total = len(results)
        return {"emails": results[filters.offset:filters.offset + filters.limit] if paginate else results,
                "total": total, "offset": filters.offset, "limit": filters.limit}

    @staticmethod
    def decorate(email, rules):
        email["category_scores"] = json.loads(email["category_scores"] or "{}")
        annotation = json.loads(email.pop("annotation", None) or "{}")
        email.update(effective_category=email["category"], effective_priority=email["priority_score"],
                     decision_source="model", task=annotation.get("task", "todo"),
                     snoozed_until=annotation.get("snoozed_until"), correction=annotation)
        if email["task"] == "snoozed" and email["snoozed_until"] and email["snoozed_until"] <= utc_now():
            email["task"] = "todo"
        for rule in rules:
            if rule["account_id"] != (email["imap_account_id"] or 0) or not rule["enabled"]:
                continue
            target = {"sender": email["sender_address"], "subject": email["subject"],
                      "text": email["subject"] + " " + email["body_preview"]}[rule["field"]]
            if rule["contains"].casefold() in target.casefold():
                if rule["category"] is not None:
                    email["effective_category"] = rule["category"]
                if rule["priority"] is not None:
                    email["effective_priority"] = rule["priority"]
                email["decision_source"] = "rule: " + rule["name"]
                break
        if annotation.get("category") is not None or annotation.get("priority") is not None:
            if annotation.get("category") is not None:
                email["effective_category"] = annotation["category"]
            if annotation.get("priority") is not None:
                email["effective_priority"] = annotation["priority"]
            email["decision_source"] = "manual"
        scores = sorted(email["category_scores"].values(), reverse=True)
        email["needs_review"] = (email["status"] == "complete" and email["decision_source"] == "model"
                                 and (not scores or scores[0] < .6 or (len(scores) > 1 and scores[0] - scores[1] < .15)))
        subject = re.sub(r"^(?:(?:re|fw|fwd|tr)\s*:\s*)+", "", email["subject"], flags=re.I).casefold()
        email["conversation"] = str(email["imap_account_id"] or 0) + ":" + (email["thread_key"] or subject + ":" + email["sender_address"].casefold())
        return email

    @staticmethod
    def matches(e, f):
        if f.demo_only and e["imap_account_id"] is not None:
            return False
        if f.conversation and e["conversation"] != f.conversation:
            return False
        if f.q.casefold() not in " ".join(str(e[k]) for k in ("sender_name", "sender_address", "subject", "body_preview")).casefold():
            return False
        if f.sender.casefold() not in e["sender_address"].casefold():
            return False
        if f.category and e["effective_category"] != f.category:
            return False
        if f.since and e["received_at"][:10] < f.since or f.until and e["received_at"][:10] > f.until:
            return False
        if (e["effective_priority"] or 0) < f.priority_min or (e["spam_score"] or 0) > f.spam_max or (e["action_score"] or 0) < f.action_min:
            return False
        if f.task != "all" and e["task"] != f.task:
            return False
        if f.todo and not (e["status"] == "complete" and e["task"] == "todo" and (e["effective_priority"] or 0) >= 58 and (e["action_score"] or 0) >= 50):
            return False
        return not f.review or e["needs_review"]

    def history(self, user_id):
        with self.db.connect() as c:
            return [dict(r) for r in c.execute("SELECT * FROM runs WHERE user_id=? ORDER BY id DESC LIMIT 200", (user_id,))]

    def views(self, user_id):
        with self.db.connect() as c:
            return [{"id": r["id"], "name": r["name"], "filters": json.loads(r["filters"])}
                    for r in c.execute("SELECT * FROM saved_views WHERE user_id=? ORDER BY id", (user_id,))]

    def save_view(self, user_id, name, filters):
        with self.db.connect() as c:
            return c.execute("INSERT INTO saved_views(user_id,name,filters) VALUES (?,?,?)",
                             (user_id, name, json.dumps(filters))).lastrowid

    def delete(self, table, record_id, user_id):
        if table not in {"personal_rules", "saved_views", "llm_connections"}:
            raise ValueError("Invalid table")
        with self.db.connect() as c:
            return c.execute(f"DELETE FROM {table} WHERE id=? AND user_id=?", (record_id, user_id)).rowcount

    def connection(self, user_id, connection_id):
        with self.db.connect() as c:
            row = c.execute("SELECT * FROM llm_connections WHERE id=? AND user_id=?", (connection_id, user_id)).fetchone()
        return dict(row) if row else None

    def connections(self, user_id):
        with self.db.connect() as c:
            return [dict(r) for r in c.execute("SELECT id,name,protocol,base_url,model,allow_remote,secret != '' AS has_secret "
                                             "FROM llm_connections WHERE user_id=? ORDER BY id", (user_id,))]

    def save_connection(self, user_id, values, connection_id=None):
        fields = ("name", "protocol", "base_url", "model", "secret", "allow_remote")
        with self.db.connect() as c:
            if connection_id:
                c.execute("UPDATE llm_connections SET name=?,protocol=?,base_url=?,model=?,secret=?,allow_remote=? "
                          "WHERE id=? AND user_id=?", (*(values[k] for k in fields), connection_id, user_id))
                return connection_id
            return c.execute("INSERT INTO llm_connections(user_id,name,protocol,base_url,model,secret,allow_remote) "
                             "VALUES (?,?,?,?,?,?,?)", (user_id, *(values[k] for k in fields))).lastrowid

    def known_ids(self, user_id, account_id, backend):
        with self.db.connect() as c:
            return {r[0] for r in c.execute("SELECT e.graph_id FROM emails e JOIN runs r ON r.id=e.run_id "
                                           "WHERE r.user_id=? AND r.imap_account_id=? AND r.model_backend=? AND e.status='complete'",
                                           (user_id, account_id, backend))}

    def save_brief(self, user_id, account_id, day, mode, payload):
        with self.db.connect() as c:
            c.execute("INSERT INTO briefs(user_id,account_id,day,mode,payload,created_at) VALUES (?,?,?,?,?,?) "
                      "ON CONFLICT(user_id,account_id,day) DO UPDATE SET mode=excluded.mode,payload=excluded.payload,created_at=excluded.created_at",
                      (user_id, account_id, day, mode, json.dumps(payload, ensure_ascii=False), utc_now()))

    def briefs(self, user_id, account_id):
        with self.db.connect() as c:
            return [{**dict(r), "payload": json.loads(r["payload"])} for r in c.execute(
                "SELECT * FROM briefs WHERE user_id=? AND account_id=? ORDER BY day DESC LIMIT 30", (user_id, account_id))]

    def comparison(self, user_id, run_id):
        run = self.db.get_run(run_id, user_id)
        reference = self.db.get_run(run["reference_run_id"], user_id) if run and run["reference_run_id"] else None
        if not reference:
            return None
        left = {e["graph_id"]: e for e in self.db.emails_for_run(reference["id"]) if e["status"] == "complete"}
        right = {e["graph_id"]: e for e in self.db.emails_for_run(run_id) if e["status"] == "complete"}
        with self.db.connect() as c:
            corrections = {r["graph_id"]: json.loads(r["payload"]).get("category") for r in c.execute(
                "SELECT * FROM annotations WHERE user_id=?", (user_id,))}
        pairs = [{"email_id": a["id"], "subject": a["subject"], "left": a["category"], "right": right[key]["category"],
                  "left_ms": a["duration_ms"], "right_ms": right[key]["duration_ms"], "expected": corrections.get(key),
                  "disagrees": a["category"] != right[key]["category"]} for key, a in left.items() if key in right]
        labeled = [p for p in pairs if p["expected"]]
        return {"run": run, "reference": reference, "pairs": pairs, "compared": len(pairs),
                "disagreements": sum(p["disagrees"] for p in pairs), "labeled": len(labeled),
                "left_accuracy": sum(p["left"] == p["expected"] for p in labeled) / len(labeled) if labeled else None,
                "right_accuracy": sum(p["right"] == p["expected"] for p in labeled) / len(labeled) if labeled else None}
