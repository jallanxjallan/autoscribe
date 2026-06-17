from __future__ import annotations

from typing import Any

from asc.scrivener.connect import LedgerConnection
from asc.scrivener.util import timestamp_now
from asc.scrivener.writers.common import (
    insert_row,
    ledger_identity,
    load_task_output,
    model_json,
    source_key,
    step_number,
)


def insert_step(*, conn: LedgerConnection, task: object) -> None:
    record = load_task_output(task)
    insert_row(conn, "steps", step_values(task, record))


def step_values(task: object, record: object | None = None) -> dict[str, Any]:
    if record is None:
        record = load_task_output(task)

    number = step_number(task)
    if number <= 0:
        raise ValueError(f"ledger step_number must be > 0: {number}")

    status = step_status(record)
    if status not in {"completed", "failed"}:
        raise ValueError(f"invalid ledger step status: {status}")

    created_at = getattr(record, "created_at", None) or getattr(task, "created_at", None) or timestamp_now()

    return {
        "identity": ledger_identity(task),
        "step_number": number,
        "result_key": source_key(task),
        "status": status,
        "content": getattr(record, "content", None),
        "fail_message": failure_message(record),
        "raw_json": model_json(record),
        "created_at": int(created_at),
    }


def step_status(record: object | None) -> str:
    explicit = getattr(record, "status", None)
    if explicit:
        return str(explicit)

    name = type(record).__name__.lower()
    if "failure" in name or "fail" in name:
        return "failed"

    if failure_message(record):
        return "failed"

    return "completed"


def failure_message(record: object | None) -> str | None:
    if record is None:
        return None

    for name in ("fail_message", "failure_reason", "error", "message"):
        value = getattr(record, name, None)
        if value:
            return str(value)

    return None


__all__ = ["failure_message", "insert_step", "step_status", "step_values"]