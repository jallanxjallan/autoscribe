from __future__ import annotations

from asc.scrivener.connect import LedgerConnection, connect
from asc.scrivener.schema import ensure_ledger_schema
from asc.scrivener.writers.calls import insert_call
from asc.scrivener.writers.common import job_action
from asc.scrivener.writers.exports import confirm_export, insert_export
from asc.scrivener.writers.steps import insert_step


CALL_ACTIONS = {"write_call", "call_started"}
STEP_ACTIONS = {"write_step", "step_written"}
EXPORT_ACTIONS = {"write_export", "call_completed", "export_written"}
CONFIRM_EXPORT_ACTIONS = {"confirm_export", "export_accepted"}


def write_job(job: object) -> None:
    with connect() as conn:
        write_job_with_connection(conn=conn, job=job)


def write_job_with_connection(*, conn: LedgerConnection, job: object) -> None:
    ensure_ledger_schema(conn)
    action = job_action(job)

    if action in CALL_ACTIONS:
        insert_call(conn=conn, job=job)
        return
    if action in STEP_ACTIONS:
        insert_step(conn=conn, job=job)
        return
    if action in EXPORT_ACTIONS:
        insert_export(conn=conn, job=job)
        return
    if action in CONFIRM_EXPORT_ACTIONS:
        confirm_export(conn=conn, job=job)
        return

    raise ValueError(f"unknown scrivener job action: {action}")


__all__ = ["write_job", "write_job_with_connection"]
