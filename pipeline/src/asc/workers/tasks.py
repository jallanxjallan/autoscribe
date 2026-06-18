"""Worker task factory.

Workers own the meaning of a plan step: engine selection, handler selection,
input content, and output content.  The orchestrator should only decide that a
worker task is next.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from asc.models.process.task import WorkerTask
from asc.redis.key import RedisKey


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    return text


def cursor_key_for(cursor: Any) -> str:
    for attr in ("key", "cursor_key"):
        value = getattr(cursor, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    identity = _required_text(getattr(cursor, "identity", None), "cursor.identity")
    return f"cursor:{identity}:index"


def content_key(identity: str, task_number: int) -> str:
    if task_number < 1:
        raise ValueError(f"invalid content task: {task_number}")
    return str(RedisKey.from_parts("result", _required_text(identity, "identity"), f"step.{int(task_number)}"))


def task_identity(call_identity: str, action: str, task_number: int) -> str:
    call_identity = _required_text(call_identity, "call_identity")
    action = _required_text(action, "action")
    return f"{call_identity}.worker.{action}.{int(task_number)}"


def json_blob(value: Mapping[str, Any] | str | None) -> str:
    if value is None:
        return "{}"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def plan_step_count(plan: Any) -> int:
    for name in ("step_count", "total_steps", "steps_count"):
        value = getattr(plan, name, None)
        if callable(value):
            value = value()
        if value not in (None, ""):
            return int(value)

    steps = getattr(plan, "steps", None)
    if isinstance(steps, str):
        try:
            steps = json.loads(steps)
        except json.JSONDecodeError:
            steps = None
    if isinstance(steps, list):
        return len(steps)

    steps_json = getattr(plan, "steps_json", None)
    if isinstance(steps_json, str) and steps_json.strip():
        loaded = json.loads(steps_json)
        if isinstance(loaded, list):
            return len(loaded)

    raise ValueError("cannot determine plan step count")


def plan_args_for_step(plan: Any, step_number: int) -> Mapping[str, Any]:
    if hasattr(plan, "args_for_step"):
        args = plan.args_for_step(step_number)
        if not isinstance(args, Mapping):
            raise ValueError("Plan.args_for_step() must return a mapping")
        return args

    steps = getattr(plan, "steps", None)
    if isinstance(steps, str):
        steps = json.loads(steps)
    if steps is None:
        steps_json = getattr(plan, "steps_json", "")
        if isinstance(steps_json, str) and steps_json.strip():
            steps = json.loads(steps_json)

    if isinstance(steps, list) and 1 <= step_number <= len(steps):
        args = steps[step_number - 1]
        if isinstance(args, Mapping):
            return args

    raise ValueError(f"cannot load plan args for step {step_number}")


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


def make_task(
    *,
    cursor: Any,
    plan: Any,
    step_number: int,
    input_key: str | None = None,
) -> WorkerTask:
    identity = _required_text(getattr(cursor, "identity", None), "cursor.identity")
    args = plan_args_for_step(plan, step_number)

    engine = step_engine_key(args.get("engine"), step_number=step_number)
    handler = step_handler_key(args, step_number=step_number)

    actual_input_key = input_key
    if actual_input_key is None:
        actual_input_key = getattr(cursor, "call_key") if step_number == 1 else content_key(identity, step_number - 1)

    return WorkerTask(
        identity=task_identity(identity, "execute-step", step_number),
        cursor_key=cursor_key_for(cursor),
        action="execute_step",
        task_number=int(step_number),
        engine=engine,
        handler=handler,
        input_model="Call" if step_number == 1 else "Result",
        input_key=_required_text(actual_input_key, "worker.input_key"),
        output_model="Result",
        output_key=content_key(identity, step_number),
        args_json=json_blob(args),
    )


__all__ = [
    "content_key",
    "cursor_key_for",
    "make_task",
    "plan_args_for_step",
    "plan_step_count",
    "step_engine_key",
    "step_handler_key",
    "task_identity",
]
