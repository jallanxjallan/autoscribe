from __future__ import annotations

"""Ledger writer for step result/failure records.

DEBT: STEPS_TABLE, STEP_STATUS_BY_MODEL_NAME, and STEP_FAILURE_NAMES belong in
asc.scrivener.contracts or asc.registries once the string contracts are gathered
next week. They stay local here for the temporary drop-in bundle.
"""

from typing import Any

from asc.scrivener.connect import LedgerConnection
from asc.scrivener.writers.common import insert_row, load_source_key, model_json, redis_key


STEPS_TABLE = "steps"
STEP_STATUS_BY_MODEL_NAME = {
    "Result": "completed",
    "StepResult": "completed",
    "Failure": "failed",
    "StepFailure": "failed",
}
STEP_FAILURE_NAMES = {"Failure", "StepFailure"}


def insert_step(*, conn: LedgerConnection, task: object) -> None:
    record = load_source_key(task.source_key)
    insert_row(conn, STEPS_TABLE, step_values(task, record))


def step_values(task: object, record: object | None = None) -> dict[str, Any]:
    if record is None:
        record = load_source_key(task.source_key)

    number = int(task.task_number)
    if number <= 0:
        raise ValueError(f"ledger step_number must be > 0: {number}")

    key = redis_key(task.source_key)
    return {
        "identity": key.identity,
        "step_number": number,
        "result_key": task.source_key,
        "status": step_status(record),
        "content": record.content,
        "fail_message": failure_message(record),
        "raw_json": model_json(record),
        "created_at": int(record.created_at),
    }


def step_status(record: object) -> str:
    name = type(record).__name__
    try:
        return STEP_STATUS_BY_MODEL_NAME[name]
    except KeyError as exc:
        expected = ", ".join(sorted(STEP_STATUS_BY_MODEL_NAME))
        raise ValueError(f"unsupported step record type: {name}; expected one of: {expected}") from exc


def failure_message(record: object) -> str | None:
    name = type(record).__name__
    if name not in STEP_FAILURE_NAMES:
        return None
    return record.fail_message


__all__ = [
    "STEPS_TABLE",
    "STEP_FAILURE_NAMES",
    "STEP_STATUS_BY_MODEL_NAME",
    "failure_message",
    "insert_step",
    "step_status",
    "step_values",
]
