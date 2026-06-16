from __future__ import annotations

from typing import Any

from asc.scrivener.connect import LedgerConnection
from asc.scrivener.queries import CONFIRM_EXPORT_SQL, INSERT_EXPORT_SQL
from asc.scrivener.util import execute_and_commit, timestamp_now
from asc.scrivener.writers.common import ledger_identity, load_cursor, load_job_input, optional, source_identity


def insert_export(*, conn: LedgerConnection, job: object) -> None:
    execute_and_commit(conn, INSERT_EXPORT_SQL, export_values(job))


def confirm_export(*, conn: LedgerConnection, job: object) -> None:
    execute_and_commit(conn, CONFIRM_EXPORT_SQL, confirm_export_values(job))


def export_values(job: object) -> tuple[Any, ...]:
    final_step = final_step_number(job)
    result_key = final_result_key(job)
    record = load_job_input(job)
    return (
        ledger_identity(job),
        source_identity(job, record),
        final_step,
        result_key,
        optional(job, "exported_at", default=None),
        optional(job, "export_message", default=None),
        int(optional(job, "created_at", default=timestamp_now())),
    )


def confirm_export_values(job: object) -> tuple[Any, ...]:
    return (
        int(optional(job, "exported_at", default=timestamp_now())),
        optional(job, "export_message", default=None),
        ledger_identity(job),
    )


def final_step_number(job: object) -> int:
    explicit = optional(job, "final_step", default=None)
    if explicit is not None:
        return int(explicit)
    step_number = int(optional(job, "step_number", default=0) or 0)
    if step_number > 0:
        return step_number
    cursor = load_cursor(job)
    for name in ("completed_step_count", "current_step", "total_steps"):
        value = optional(cursor, name, default=None)
        if value:
            return int(value)
    raise ValueError("export job missing final step number")


def final_result_key(job: object) -> str:
    explicit = optional(job, "result_key", default=None)
    if explicit:
        return str(explicit)
    for name in ("input_key", "output_key"):
        value = str(optional(job, name, default="") or "")
        if ":result." in value or ":failure." in value:
            return value
    output_key = optional(job, "output_key", default=None)
    if output_key:
        return str(output_key)
    raise ValueError("export job missing final result key")


__all__ = [
    "confirm_export",
    "confirm_export_values",
    "export_values",
    "final_result_key",
    "final_step_number",
    "insert_export",
]
