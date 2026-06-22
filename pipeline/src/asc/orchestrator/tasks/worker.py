"""Worker task and materialized step factories used by orchestrator handlers.

The orchestrator compiles a Plan into short-lived Step records once, stores the
Step keys in the call/results index, and sends Worker tasks containing only the
Call key plus the Step key.  Workers should not load or unpack the Plan.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from asc.models.process.step import Step
from asc.models.process.task import Task
from asc.redis.key import RedisKey

from ..contracts import WORKER_EXECUTE_STEP


WORKER_PACKAGE = "worker"


def make_worker_step(
    *,
    call_key: str,
    step_key: str,
    step_number: int,
    cursor_key: str | None = None,
) -> Task:
    """Create the compact Worker task for one materialized Step."""

    step_number = int(step_number)
    data: dict[str, object] = {
        "identity": _task_identity(call_key=call_key, step_number=step_number),
        "package": WORKER_PACKAGE,
        "action": WORKER_EXECUTE_STEP,
        "source_key": str(step_key),
        "call_key": str(call_key),
        "step_key": str(step_key),
        "task_number": step_number,
        "args_json": "{}",
        "ttl_seconds": None,
    }
    if cursor_key is not None:
        data["cursor_key"] = str(cursor_key)
    return Task(**data)


def materialize_plan_steps(
    *,
    call_key: str | RedisKey,
    cursor_key: str,
    plan: Any,
    call_index: Any,
    ttl_seconds: int | None = None,
) -> list[str]:
    """Save Step records for every Plan step and put their keys in the index."""

    call = RedisKey(str(call_key))
    step_keys: list[str] = []

    for step_number, raw_step in enumerate(plan_steps(plan), start=1):
        step = make_step_record(
            call_key=str(call),
            cursor_key=cursor_key,
            call_identity=call.identity,
            step_number=step_number,
            raw_step=raw_step,
            ttl_seconds=ttl_seconds,
        )
        step.save()
        step_key = str(step.redis_key)
        call_index.set_slot(step_number, step_key)
        step_keys.append(step_key)

    return step_keys


def make_step_record(
    *,
    call_key: str,
    cursor_key: str,
    call_identity: str,
    step_number: int,
    raw_step: Any,
    ttl_seconds: int | None = None,
) -> Step:
    """Compile one plan step mapping into a short-lived Step record."""

    step = _mapping(raw_step, field_name=f"plan step {step_number}")
    args = _mapping(step.get("args", {}), field_name=f"plan step {step_number} args")

    data: dict[str, Any] = {}
    data.update(step)
    for key, value in args.items():
        data.setdefault(key, value)

    data.update(
        {
            "identity": f"{call_identity}.step.{step_number}",
            "call_key": call_key,
            "cursor_key": cursor_key,
            "step_number": step_number,
            "executor": step_executor_key(data, step_number=step_number),
            "action": step_action_key(data, step_number=step_number),
            "instructions_json": json.dumps(
                step_instruction_keys(data),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "args_json": json.dumps(
                args,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            ),
            "ttl_seconds": ttl_seconds,
        }
    )
    return Step(**data)


def plan_step_count(plan: Any) -> int:
    value = getattr(plan, "step_count", None)
    if callable(value):
        return int(value())
    if value not in (None, ""):
        return int(value)

    value = getattr(plan, "total_steps", None)
    if callable(value):
        return int(value())
    if value not in (None, ""):
        return int(value)

    return len(plan_steps(plan))


def plan_steps(plan: Any) -> list[Any]:
    steps = getattr(plan, "steps", None)
    if callable(steps):
        steps = steps()
    if isinstance(steps, str):
        steps = json.loads(steps)
    if steps is None:
        steps = json.loads(getattr(plan, "steps_json"))
    if not isinstance(steps, list):
        raise ValueError("plan.steps must be a list")
    return steps


def step_executor_key(args: Mapping[str, Any], *, step_number: int) -> str:
    value = args.get("executor") or args.get("engine") or args.get("kind")
    text = _ref_text(value)
    if not text:
        raise ValueError(f"plan step {step_number} has no executor/engine")
    return text.removeprefix("engines.").replace("-", "_")


def step_action_key(args: Mapping[str, Any], *, step_number: int) -> str:
    value = args.get("action") or args.get("handler") or args.get("script") or args.get("model")
    text = _ref_text(value)
    if text:
        return text
    return step_executor_key(args, step_number=step_number)


def step_instruction_keys(args: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for name in ("instruction_keys", "instruction_slugs", "instructions"):
        raw = args.get(name)
        if raw is None or raw == "":
            continue
        if not isinstance(raw, list):
            raise ValueError(f"{name} must be a list")
        values.extend(_required_ref_text(item, field_name=f"{name}[]") for item in raw)

    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def _task_identity(*, call_key: str, step_number: int) -> str:
    call = RedisKey(str(call_key))
    return f"{call.identity}.worker.{WORKER_EXECUTE_STEP}.{int(step_number)}"


def _mapping(value: Any, *, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    return dict(value)


def _required_ref_text(value: object, *, field_name: str) -> str:
    text = _ref_text(value)
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    return text


def _ref_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        for key in ("key", "slug", "record_identity", "identity", "module", "name"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return str(value).strip()


__all__ = [
    "make_step_record",
    "make_worker_step",
    "materialize_plan_steps",
    "plan_step_count",
    "plan_steps",
    "step_action_key",
    "step_executor_key",
    "step_instruction_keys",
]
