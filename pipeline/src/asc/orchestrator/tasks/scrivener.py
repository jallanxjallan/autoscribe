"""Scrivener task factories.

Scrivener-owned task construction lives here.  The orchestrator decides that a
ledger write is next; this module owns the shape of that scrivener task.
"""

from __future__ import annotations

from typing import Any

from .common import ScrivenerTask, WorkerTask, cursor_key_for, required_text, task_number_for


def task_identity(call_identity: str, action: str, task_number: int = 0) -> str:
    call_identity = required_text(call_identity, "call_identity")
    action = required_text(action, "action")
    if int(task_number):
        return f"{call_identity}.scrivener.{action}.{int(task_number)}"
    return f"{call_identity}.scrivener.{action}"


def make_scrivener_call_task(cursor: Any) -> ScrivenerTask:
    identity = required_text(getattr(cursor, "identity", None), "cursor.identity")
    call_key = required_text(getattr(cursor, "call_key", None), "cursor.call_key")

    return ScrivenerTask(
        identity=task_identity(identity, "write_call"),
        task_number=0,
        cursor_key=cursor_key_for(cursor),
        action="write_call",
        source_key=call_key,
        ledger_table="calls",
    )


def make_scrivener_step_task(*, cursor: Any, worker_task: WorkerTask) -> ScrivenerTask:
    identity = required_text(getattr(cursor, "identity", None), "cursor.identity")
    task_number = task_number_for(worker_task)
    source_key = required_text(getattr(worker_task, "output_key", None), "worker_task.output_key")

    return ScrivenerTask(
        identity=task_identity(identity, "write_step", task_number),
        task_number=task_number,
        cursor_key=cursor_key_for(cursor),
        action="write_step",
        source_key=source_key,
        ledger_table="steps",
    )


def make_scrivener_result_task(*, cursor: Any, previous_task: ScrivenerTask) -> ScrivenerTask:
    identity = required_text(getattr(cursor, "identity", None), "cursor.identity")
    task_number = task_number_for(previous_task)
    source_key = required_text(getattr(previous_task, "source_key", None), "previous_task.source_key")

    return ScrivenerTask(
        identity=task_identity(identity, "call_completed", task_number),
        task_number=task_number,
        cursor_key=cursor_key_for(cursor),
        action="call_completed",
        source_key=source_key,
        ledger_table="exports",
        final_step=task_number,
        exported_at="",
        export_message="",
    )


# Compatibility for older call sites/tests.
make_call_task = make_scrivener_call_task
make_step_task = make_scrivener_step_task
make_result_task = make_scrivener_result_task


__all__ = [
    "make_call_task",
    "make_result_task",
    "make_scrivener_call_task",
    "make_scrivener_result_task",
    "make_scrivener_step_task",
    "make_step_task",
    "task_identity",
]
