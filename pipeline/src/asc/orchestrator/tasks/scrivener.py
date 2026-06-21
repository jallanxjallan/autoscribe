"""Scrivener task factories used by orchestrator handlers."""

from __future__ import annotations

import json
from typing import Any

from asc.models.process.task import ScrivenerTask

from ..contracts import (
    SCRIVENER_CALL_COMPLETED,
    SCRIVENER_CALL_FAILED,
    SCRIVENER_WRITE_CALL,
    SCRIVENER_WRITE_STEP,
)


def make_scrivener_write_call(cursor: Any) -> ScrivenerTask:
    return ScrivenerTask(
        identity=f"{cursor.identity}.scrivener.{SCRIVENER_WRITE_CALL}.0",
        action=SCRIVENER_WRITE_CALL,
        source_key=cursor.call_key,
        cursor_key=cursor.key,
        plan_key=cursor.plan_key,
        task_number=0,
        args_json="{}",
        ttl_seconds=None,
    )


def make_scrivener_write_step(*, cursor: Any, response_key: str, step_number: int) -> ScrivenerTask:
    return ScrivenerTask(
        identity=f"{cursor.identity}.scrivener.{SCRIVENER_WRITE_STEP}.{int(step_number)}",
        action=SCRIVENER_WRITE_STEP,
        source_key=response_key,
        cursor_key=cursor.key,
        plan_key=cursor.plan_key,
        task_number=int(step_number),
        args_json="{}",
        ttl_seconds=None,
    )


def make_scrivener_call_completed(*, cursor: Any, completed_after_step: int) -> ScrivenerTask:
    task_number = int(completed_after_step) + 1
    return ScrivenerTask(
        identity=f"{cursor.identity}.scrivener.{SCRIVENER_CALL_COMPLETED}.{task_number}",
        action=SCRIVENER_CALL_COMPLETED,
        source_key=cursor.call_key,
        cursor_key=cursor.key,
        plan_key=cursor.plan_key,
        task_number=task_number,
        args_json=json.dumps(
            {"completed_after_step": int(completed_after_step)},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        ttl_seconds=None,
    )


def make_scrivener_call_failed(*, cursor: Any, failure_key: str, failed_at_step: int, failure: Any) -> ScrivenerTask:
    step_number = int(failed_at_step)
    return ScrivenerTask(
        identity=f"{cursor.identity}.scrivener.{SCRIVENER_CALL_FAILED}.{step_number}",
        action=SCRIVENER_CALL_FAILED,
        source_key=failure_key,
        cursor_key=cursor.key,
        plan_key=cursor.plan_key,
        task_number=step_number,
        args_json=json.dumps(
            {
                "failed_at_step": step_number,
                "failure_key": failure_key,
                "failure_repr": repr(failure),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        ttl_seconds=None,
    )


__all__ = [
    "make_scrivener_call_completed",
    "make_scrivener_call_failed",
    "make_scrivener_write_call",
    "make_scrivener_write_step",
]
