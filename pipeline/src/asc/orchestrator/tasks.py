"""Task factories used by orchestrator handlers.

These are deliberately explicit and boring.  Longer term, these constructors can
move beside the receiving packages, but the routing code should still produce a
task, save it, and post only that task key to the receiving inbox.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from asc.models.process.task import ScrivenerTask, WorkerTask

from .contracts import (
    SCRIVENER_CALL_COMPLETED,
    SCRIVENER_CALL_FAILED,
    SCRIVENER_WRITE_CALL,
    SCRIVENER_WRITE_STEP,
    WORKER_EXECUTE_STEP,
)


def task_key(task: Any) -> str:
    return str(task.key)


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


def make_worker_step(*, cursor: Any, plan: Any, step_number: int, input_key: str) -> WorkerTask:
    step_number = int(step_number)
    args = dict(plan_args_for_step(plan, step_number))
    args.setdefault("results_index_key", f"results:{cursor.identity}:index")
    args.setdefault("success_key", f"response:{cursor.identity}:{step_number}")
    args.setdefault("failure_key", f"failure:{cursor.identity}:{step_number}")
    return WorkerTask(
        identity=f"{cursor.identity}.worker.{WORKER_EXECUTE_STEP}.{step_number}",
        cursor_key=cursor.key,
        action=WORKER_EXECUTE_STEP,
        task_number=step_number,
        step_number=step_number,
        engine=step_engine_key(args.get("engine"), step_number=step_number),
        handler=step_handler_key(args, step_number=step_number),
        input_model="Call" if step_number == 1 else "Response",
        input_key=input_key,
        output_model="Result",
        output_key=f"results:{cursor.identity}:index",
        args_json=json.dumps(args, ensure_ascii=False, separators=(",", ":")),
    )


def plan_step_count(plan: Any) -> int:
    value = getattr(plan, "step_count", None)
    if callable(value):
        return int(value())
    if value not in (None, ""):
        return int(value)
    return len(plan_steps(plan))


def plan_steps(plan: Any) -> list[Any]:
    steps = getattr(plan, "steps", None)
    if isinstance(steps, str):
        steps = json.loads(steps)
    if steps is None:
        steps = json.loads(getattr(plan, "steps_json"))
    if not isinstance(steps, list):
        raise ValueError("plan.steps must be a list")
    return steps


def plan_args_for_step(plan: Any, step_number: int) -> Mapping[str, Any]:
    args_for_step = getattr(plan, "args_for_step", None)
    if callable(args_for_step):
        args = args_for_step(step_number)
    else:
        args = plan_steps(plan)[int(step_number) - 1]
    if not isinstance(args, Mapping):
        raise ValueError(f"plan step {step_number} must be a mapping")
    return args


def step_engine_key(value: object, *, step_number: int) -> str:
    if isinstance(value, str):
        text = value.strip()
    elif isinstance(value, Mapping):
        raw = value.get("key") or value.get("slug") or value.get("name")
        text = str(raw).strip() if raw is not None else ""
    else:
        text = ""
    if not text:
        raise ValueError(f"plan step {step_number} has no engine")
    return text.removeprefix("engines.").replace("-", "_")


def step_handler_key(args: Mapping[str, Any], *, step_number: int) -> str:
    value = args.get("handler") or args.get("script") or args.get("model")
    if isinstance(value, Mapping):
        value = value.get("key") or value.get("slug") or value.get("name")
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"plan step {step_number} has no handler/script/model")
    return text


__all__ = [
    "make_scrivener_call_completed",
    "make_scrivener_call_failed",
    "make_scrivener_write_call",
    "make_scrivener_write_step",
    "make_worker_step",
    "plan_step_count",
    "task_key",
]
