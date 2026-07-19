"""Persist call records and terminal success responses from key-only inbox entries."""

from __future__ import annotations

from dataclasses import dataclass
import json

from asc.ledger.connect import connect
from asc.ledger.schema import ensure_ledger_schema
from asc.ledger.sql import insert_row
from asc.ledger.write import write_key
from asc.redis.key import RedisKey


@dataclass(frozen=True, slots=True)
class ScrivenerExecutionReport:
    artifact_key: str
    kind: str
    table: str


class ScrivenerExecutor:
    def execute(self, artifact_key: str) -> ScrivenerExecutionReport:
        key = RedisKey(str(artifact_key).strip())
        if key.kind == "call":
            write_key(key)
            return ScrivenerExecutionReport(key.raw_key, "call", "calls")
        if key.kind == "response":
            _write_terminal_response(key)
            return ScrivenerExecutionReport(key.raw_key, "response", "responses")
        raise ValueError(f"scrivener accepts only call and terminal response keys: {key.raw_key}")


def _write_terminal_response(key: RedisKey) -> None:
    raw = key.hgetall()
    if not raw:
        raise KeyError(f"response record does not exist: {key.raw_key}")
    ordinal = int(raw.get("ordinal", key.suffix or 0))
    if ordinal < 1:
        raise ValueError(f"terminal response has invalid ordinal: {key.raw_key}")
    raw_json = raw.get("raw_json", "{}")
    try:
        json.loads(raw_json)
    except json.JSONDecodeError:
        raw_json = json.dumps(raw_json, ensure_ascii=False)
    row = {
        "identity": key.identity,
        "final_step": ordinal,
        "result_key": key.raw_key,
        "result_kind": "response",
        "status": "success",
        "content": raw.get("content"),
        "fail_message": None,
        "raw_json": raw_json,
        "created_at": int(raw.get("created_at", 0)),
    }
    with connect() as conn:
        ensure_ledger_schema(conn)
        insert_row(conn, table="responses", data=row)


__all__ = ["ScrivenerExecutionReport", "ScrivenerExecutor"]
