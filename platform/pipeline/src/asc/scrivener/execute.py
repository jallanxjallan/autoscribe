"""Persist call records and terminal successful Results.

Scrivener owns one long-lived ledger connection. Schema setup is performed by
its daemon before the claim loop starts; individual artifacts never initialize
or migrate the schema.
"""

from __future__ import annotations

from dataclasses import dataclass
import json

from asc.ledger.connect import LedgerConnection
from asc.ledger.sql import insert_row
from asc.ledger.write import write_key_with_connection
from asc.models.process.result import SUCCESS_RESULT_KINDS, load_result
from asc.redis.key import RedisKey


@dataclass(frozen=True, slots=True)
class ScrivenerExecutionReport:
    artifact_key: str
    kind: str
    table: str


class ScrivenerExecutor:
    """Persist artifacts through an already-initialized ledger connection."""

    def __init__(self, conn: LedgerConnection) -> None:
        self.conn = conn

    def execute(self, artifact_key: str) -> ScrivenerExecutionReport:
        key = RedisKey(str(artifact_key).strip())

        if key.kind == "call":
            write_key_with_connection(conn=self.conn, key=key)
            return ScrivenerExecutionReport(key.raw_key, "call", "calls")

        if key.kind in SUCCESS_RESULT_KINDS:
            _write_terminal_result(self.conn, key)
            return ScrivenerExecutionReport(key.raw_key, key.kind, "results")

        raise ValueError(
            f"scrivener accepts only call and successful result keys: {key.raw_key}"
        )


def _write_terminal_result(conn: LedgerConnection, key: RedisKey) -> None:
    result = load_result(key)
    row = {
        "identity": result.identity,
        "final_step": result.ordinal,
        "result_key": key.raw_key,
        "result_kind": key.kind,
        "status": "success",
        "content": result.content,
        "fail_message": None,
        "raw_json": json.dumps(
            result.raw_json,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "created_at": result.created_at,
    }
    insert_row(conn, table="results", data=row)


__all__ = ["ScrivenerExecutionReport", "ScrivenerExecutor"]
