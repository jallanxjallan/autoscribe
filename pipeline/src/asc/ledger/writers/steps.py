"""Ledger writer for step result/failure records.

DEBT: STEPS_TABLE, STEP_STATUS_BY_MODEL_NAME, and STEP_FAILURE_NAMES belong in
asc.scrivener.contracts or asc.registries once the string contracts are gathered.
"""

from typing import Any

from asc.ledger.connect import LedgerConnection
from asc.ledger.writers.common import (
    insert_row,
    load_task_record,
    model_json,
    task_call_identity,
    task_record_key_text,
)


STEPS_TABLE = "steps"
STEP_STATUS_BY_MODEL_NAME = {
    "Result": "completed",
    "StepResult": "completed",
    "Failure": "failed",
    "StepFailure": "failed",
}
STEP_FAILURE_NAMES = {"Failure", "StepFailure"}


def insert_step(*, conn: LedgerConnection, task: object) -> None:
    record = load_task_record(task)
    insert_row(conn, STEPS_TABLE, step_values(task, record))


def step_values(task: Any, record: object | None = None) -> dict[str, Any]:
    if record is None:
        record = load_task_record(task)

    step_number = int(task.task_number)
    if step_number <= 0:
        raise ValueError(f"ledger step_number must be > 0: {step_number}")

    return {
        "identity": task_call_identity(task),
        "step_number": step_number,
        "result_key": task_record_key_text(task),
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
    if type(record).__name__ not in STEP_FAILURE_NAMES:
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
