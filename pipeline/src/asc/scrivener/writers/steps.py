from __future__ import annotations

from typing import Any

from asc.scrivener.connect import LedgerConnection
from asc.scrivener.queries import INSERT_STEP_SQL
from asc.scrivener.util import execute_and_commit, timestamp_now
from asc.scrivener.writers.common import (
    ledger_identity,
    load_job_output,
    optional,
    record_blob,
    required,
)


def insert_step(*, conn: LedgerConnection, job: object) -> None:
    execute_and_commit(conn, INSERT_STEP_SQL, step_values(job))


def step_values(job: object) -> tuple[Any, ...]:
    record = load_job_output(job)
    step_number = int(required(job, "step_number"))
    if step_number <= 0:
        raise ValueError(f"ledger step_number must be > 0: {step_number}")

    status = step_status(job, record)
    if status not in {"completed", "failed"}:
        raise ValueError(f"invalid ledger step status: {status}")

    return (
        ledger_identity(job),
        step_number,
        str(required(job, "output_key")),
        status,
        optional(record, "content", default=None),
        failure_message(record),
        record_blob(record, fallback=job),
        int(optional(record, "created_at", default=optional(job, "created_at", default=timestamp_now()))),
    )


def step_status(job: object, record: object | None) -> str:
    explicit = optional(job, "status", default=None)
    if explicit:
        return str(explicit)
    output_model = str(optional(job, "output_model", default="")).lower()
    if "failure" in output_model or "fail" in output_model:
        return "failed"
    if failure_message(record):
        return "failed"
    return "completed"


def failure_message(record: object | None) -> str | None:
    for name in ("fail_message", "failure_reason", "error", "message"):
        value = optional(record, name, default=None)
        if value:
            return str(value)
    return None


__all__ = ["failure_message", "insert_step", "step_status", "step_values"]
