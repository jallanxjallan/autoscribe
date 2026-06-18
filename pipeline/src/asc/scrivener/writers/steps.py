from __future__ import annotations

from typing import Any

from asc.scrivener.connect import LedgerConnection
from asc.scrivener.writers.common import insert_row, ledger_identity, load_task_output, model_json, source_key, step_number


def insert_step(*, conn: LedgerConnection, task: object) -> None:
    record = load_task_output(task)
    insert_row(conn, "steps", step_values(task, record))


def step_values(task: object, record: object | None = None) -> dict[str, Any]:
    if record is None:
        record = load_task_output(task)

    number = step_number(task)
    if number <= 0:
        raise ValueError(f"ledger step_number must be > 0: {number}")

    return {
        "identity": ledger_identity(task),
        "step_number": number,
        "result_key": source_key(task),
        "status": step_status(record),
        "content": record.content,
        "fail_message": failure_message(record),
        "raw_json": model_json(record),
        "created_at": int(record.created_at),
    }


def step_status(record: object) -> str:
    name = type(record).__name__
    if name == "StepResult":
        return "completed"
    if name == "StepFailure":
        return "failed"
    raise ValueError(f"unsupported step record type: {name}")


def failure_message(record: object) -> str | None:
    if type(record).__name__ == "StepResult":
        return None
    return record.fail_message


__all__ = ["failure_message", "insert_step", "step_status", "step_values"]
