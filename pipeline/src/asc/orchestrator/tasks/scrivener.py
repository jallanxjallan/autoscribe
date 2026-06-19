from __future__ import annotations

import json

from asc.models.process.cursor import Cursor
from asc.models.process.task import ScrivenerTask


# DEBT:
# These task action strings should move into asc.registries or
# asc.scrivener.contracts next week. Keep them local for now so the
# orchestration flow remains easy to follow during the current refactor.
WRITE_CALL = "write_call"
WRITE_STEP = "write_step"
CALL_COMPLETED = "call_completed"


def task_identity(identity: str, action: str, task_number: int) -> str:
    return f"{identity}.scrivener.{action}.{task_number}"


def make_scrivener_call_task(*, cursor: Cursor) -> ScrivenerTask:
    task_number = 0

    return ScrivenerTask(
        identity=task_identity(cursor.identity, WRITE_CALL, task_number),
        action=WRITE_CALL,
        source_key=cursor.call_key,
        cursor_key=cursor.key,
        plan_key=cursor.plan_key,
        task_number=task_number,
        args_json="{}",
        ttl_seconds=None,
    )


def make_scrivener_step_task(
    *,
    cursor: Cursor,
    source_key: str,
    task_number: int,
) -> ScrivenerTask:
    return ScrivenerTask(
        identity=task_identity(cursor.identity, WRITE_STEP, task_number),
        action=WRITE_STEP,
        source_key=source_key,
        cursor_key=cursor.key,
        plan_key=cursor.plan_key,
        task_number=task_number,
        args_json="{}",
        ttl_seconds=None,
    )


def make_scrivener_result_task(
    *,
    cursor: Cursor,
    previous_task: ScrivenerTask,
) -> ScrivenerTask:
    task_number = previous_task.task_number + 1

    return ScrivenerTask(
        identity=task_identity(cursor.identity, CALL_COMPLETED, task_number),
        action=CALL_COMPLETED,
        source_key=cursor.call_key,
        cursor_key=cursor.key,
        plan_key=cursor.plan_key,
        task_number=task_number,
        args_json=json.dumps(
            {
                "previous_task_key": previous_task.key,
                "completed_after_task_number": previous_task.task_number,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        ttl_seconds=None,
    )