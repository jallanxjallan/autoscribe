"""Worker task factory.

Worker-owned task construction lives here.  The orchestrator decides that a
worker step is next; this module owns the shape of that worker task.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from asc.redis.key import RedisKey

from .common import WorkerTask, cursor_key_for, required_text


def result_key(identity: str, task_number: int) -> str:
    if int(task_number) < 1:
        raise ValueError(f"invalid result task number: {task_number}")
    return str(RedisKey.from_parts("result", required_text(identity, "identity"), f"step.{int(task_number)}"))


# Compatibility for older call sites/tests.
content_key = result_key


def task_identity(call_identity: str, action: str, task_number: int) -> str:
    call_identity = required_text(call_identity, "call_identity")
    action = required_text(action, "action")
    return f"{call_identity}.worker.{action}.{int(task_number)}"


def json_blob(value: Mapping[str, Any] | str | None) -> str:
    if value is None:
        return "{}"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _steps_from_plan(plan: Any) -> list[Any]:
    steps = getattr(plan, "steps", None)
    if isinstance(steps, str):
        steps = json.loads(steps)
    if steps is None:
        steps_json = getattr(plan, "steps_json", "")
        if isinstance(steps_json, str) and steps_json.strip():
            steps = json.loads(steps_json)
    if not isinstance(steps, list):
        raise ValueError("plan.steps must be a list")
    return steps


def plan_step_count(plan: Any) -> int:
    for name in ("step_count", "total_steps", "steps_count"):
        value = getattr(plan, name, None)
        if callable(value):
            value = value()
        if value not in (None, ""):
            return int(value)
    return len(_steps_from_plan(plan))


def plan_args_for_step(plan: Any, step_number: int) -> Mapping[str, Any]:
    if int(step_number) < 1:
        raise ValueError(f"invalid plan step: {step_number}")

    args_for_step = getattr(plan, "args_for_step", None)
    if callable(args_for_step):
        args = args_for_step(step_number)
        if not isinstance(args, Mapping):
            raise ValueError("Plan.args_for_step() must return a mapping")
        return args

    steps = _steps_from_plan(plan)
    if int(step_number) > len(steps):
        raise ValueError(f"plan has no step {step_number}")

    args = steps[int(step_number) - 1]
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


def make_worker_task(
    *,
    cursor: Any,
    plan: Any,
    step_number: int,
    input_key: str | None = None,
) -> WorkerTask:
    identity = required_text(getattr(cursor, "identity", None), "cursor.identity")
    step_number = int(step_number)
    args = plan_args_for_step(plan, step_number)

    actual_input_key = input_key
    if actual_input_key is None:
        actual_input_key = getattr(cursor, "call_key", None) if step_number == 1 else result_key(identity, step_number - 1)

    return WorkerTask(
        identity=task_identity(identity, "execute-step", step_number),
        cursor_key=cursor_key_for(cursor),
        action="execute_step",
        task_number=step_number,
        step_number=step_number,
        engine=step_engine_key(args.get("engine"), step_number=step_number),
        handler=step_handler_key(args, step_number=step_number),
        input_model="Call" if step_number == 1 else "Result",
        input_key=required_text(actual_input_key, "worker.input_key"),
        output_model="Result",
        output_key=result_key(identity, step_number),
        args_json=json_blob(args),
    )


# Compatibility for the previous split module name.
make_task = make_worker_task


__all__ = [
    "content_key",
    "json_blob",
    "make_task",
    "make_worker_task",
    "plan_args_for_step",
    "plan_step_count",
    "result_key",
    "step_engine_key",
    "step_handler_key",
    "task_identity",
]
