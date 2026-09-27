from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .ids import new_ulid

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS calls_v1 (
    identity TEXT PRIMARY KEY,
    schema_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    source_repo TEXT NOT NULL,
    source_repo_name TEXT NOT NULL,
    source_commit TEXT NOT NULL,
    source_ref TEXT,
    plan_id TEXT NOT NULL,
    plan_ref TEXT NOT NULL,
    plan_label TEXT NOT NULL,
    plan_type TEXT,
    canonical_json TEXT NOT NULL,
    UNIQUE(source_repo, source_commit, plan_id)
);

CREATE TABLE IF NOT EXISTS call_events_v1 (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    call_identity TEXT NOT NULL REFERENCES calls_v1(identity),
    event TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    detail_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_call_events_v1_call_seq
ON call_events_v1(call_identity, seq);

CREATE TABLE IF NOT EXISTS responses_v1 (
    identity TEXT PRIMARY KEY,
    call_identity TEXT NOT NULL REFERENCES calls_v1(identity),
    runtime_key TEXT NOT NULL,
    task_key TEXT NOT NULL UNIQUE,
    source_identity TEXT NOT NULL,
    executor TEXT NOT NULL,
    entrypoint TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_responses_v1_call
ON responses_v1(call_identity, created_at);

CREATE VIEW IF NOT EXISTS call_state_v1 AS
SELECT c.*,
       (SELECT e.event FROM call_events_v1 e
        WHERE e.call_identity = c.identity
        ORDER BY e.seq DESC LIMIT 1) AS latest_event,
       (SELECT e.created_at FROM call_events_v1 e
        WHERE e.call_identity = c.identity
        ORDER BY e.seq DESC LIMIT 1) AS latest_event_at
FROM calls_v1 c;

CREATE TRIGGER IF NOT EXISTS calls_v1_no_update
BEFORE UPDATE ON calls_v1 BEGIN
  SELECT RAISE(ABORT, 'calls_v1 is append-only');
END;
CREATE TRIGGER IF NOT EXISTS calls_v1_no_delete
BEFORE DELETE ON calls_v1 BEGIN
  SELECT RAISE(ABORT, 'calls_v1 is append-only');
END;
CREATE TRIGGER IF NOT EXISTS call_events_v1_no_update
BEFORE UPDATE ON call_events_v1 BEGIN
  SELECT RAISE(ABORT, 'call_events_v1 is append-only');
END;
CREATE TRIGGER IF NOT EXISTS call_events_v1_no_delete
BEFORE DELETE ON call_events_v1 BEGIN
  SELECT RAISE(ABORT, 'call_events_v1 is append-only');
END;
CREATE TRIGGER IF NOT EXISTS responses_v1_no_update
BEFORE UPDATE ON responses_v1 BEGIN
  SELECT RAISE(ABORT, 'responses_v1 is append-only');
END;
CREATE TRIGGER IF NOT EXISTS responses_v1_no_delete
BEFORE DELETE ON responses_v1 BEGIN
  SELECT RAISE(ABORT, 'responses_v1 is append-only');
END;
"""


class LedgerError(RuntimeError):
    pass


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    return db


def ensure_schema(path: Path) -> None:
    with connect(path) as db:
        db.executescript(_SCHEMA)


def _semantic_json(call: dict) -> str:
    semantic = dict(call)
    semantic.pop("created_at", None)
    return json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def record_call(path: Path, call: dict) -> tuple[str, bool]:
    ensure_schema(path)
    source = call["source"]
    plan = call["plan"]
    canonical = json.dumps(call, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    identity = new_ulid()
    with connect(path) as db:
        cur = db.execute(
            """
            INSERT OR IGNORE INTO calls_v1 (
                identity, schema_name, created_at,
                source_repo, source_repo_name, source_commit, source_ref,
                plan_id, plan_ref, plan_label, plan_type, canonical_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identity, call["schema"], call["created_at"],
                source["repo"], source["repo_name"], source["commit"], source.get("ref"),
                plan["id"], plan["ref"], plan["label"], plan.get("plan_type"), canonical,
            ),
        )
        created = cur.rowcount == 1
        if created:
            db.execute(
                "INSERT INTO call_events_v1(call_identity, event, detail_json) VALUES (?, 'recorded', '{}')",
                (identity,),
            )
            return identity, True
        row = db.execute(
            """
            SELECT identity, canonical_json FROM calls_v1
            WHERE source_repo = ? AND source_commit = ? AND plan_id = ?
            """,
            (source["repo"], source["commit"], plan["id"]),
        ).fetchone()
        if row is None:
            raise LedgerError("call insert was ignored but existing call was not found")
        existing = json.loads(row["canonical_json"])
        if _semantic_json(existing) != _semantic_json(call):
            raise LedgerError("same repo/commit/plan resolved to different canonical call content")
        return str(row["identity"]), False


def append_event(path: Path, call_identity: str, event: str, detail: dict | None = None) -> None:
    ensure_schema(path)
    detail_json = json.dumps(detail or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    with connect(path) as db:
        db.execute(
            "INSERT INTO call_events_v1(call_identity, event, detail_json) VALUES (?, ?, ?)",
            (call_identity, event, detail_json),
        )


def has_event(path: Path, call_identity: str, event: str) -> bool:
    ensure_schema(path)
    with connect(path) as db:
        row = db.execute(
            "SELECT 1 FROM call_events_v1 WHERE call_identity = ? AND event = ? LIMIT 1",
            (call_identity, event),
        ).fetchone()
    return row is not None


def load_call(path: Path, call_identity: str) -> dict:
    ensure_schema(path)
    with connect(path) as db:
        row = db.execute(
            "SELECT canonical_json FROM calls_v1 WHERE identity = ?",
            (call_identity,),
        ).fetchone()
    if row is None:
        raise LedgerError(f"unknown call identity: {call_identity}")
    return json.loads(row["canonical_json"])


def record_response(
    path: Path, *, call_identity: str, runtime_key: str, task_key: str,
    source_identity: str, executor: str, entrypoint: str, content: str,
) -> tuple[str, bool]:
    ensure_schema(path)
    identity = new_ulid()
    with connect(path) as db:
        cur = db.execute(
            """
            INSERT OR IGNORE INTO responses_v1(
                identity, call_identity, runtime_key, task_key, source_identity,
                executor, entrypoint, content
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (identity, call_identity, runtime_key, task_key, source_identity, executor, entrypoint, content),
        )
        if cur.rowcount == 1:
            return identity, True
        row = db.execute("SELECT identity FROM responses_v1 WHERE task_key = ?", (task_key,)).fetchone()
        if row is None:
            raise LedgerError(f"could not record response for task: {task_key}")
        return str(row["identity"]), False


def load_response(path: Path, response_identity: str) -> dict:
    ensure_schema(path)
    with connect(path) as db:
        row = db.execute("SELECT * FROM responses_v1 WHERE identity = ?", (response_identity,)).fetchone()
    if row is None:
        raise LedgerError(f"unknown response identity: {response_identity}")
    return dict(row)
