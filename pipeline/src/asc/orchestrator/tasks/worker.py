"""Worker task factories used by orchestrator handlers.

The generic WorkerTask factory lives in its own module so the package can later
split execution into worker.llm, worker.script, worker.rag, etc. without turning
orchestrator task construction into a mixed-purpose junk drawer.
"""

import json
from typing import Any, Mapping

from asc.models.process.task import WorkerTask

from ..contracts import WORKER_EXECUTE_STEP


def make_worker_step(*, cursor: Any, plan: Any, step_number: int, input_key: str) -> WorkerTask:
    step_number = int(step_number)
    task_identity = f"{cursor.identity}.worker.{WORKER_EXECUTE_STEP}.{step_number}"
    response_key = f"response:{task_identity}"
    failure_key = f"failure:{task_identity}"

    args = dict(plan_args_for_step(plan, step_number))
    args.setdefault("success_key", response_key)
    args.setdefault("failure_key", failure_key)

    return WorkerTask(
        identity=task_identity,
        cursor_key=str(cursor.redis_key),
        action=WORKER_EXECUTE_STEP,
        task_number=step_number,
        step_number=step_number,
        engine=step_engine_key(args.get("engine"), step_number=step_number),
        handler=step_handler_key(args, step_number=step_number),
        input_model="Call" if step_number == 1 else "Response",
        input_key=str(input_key),
        output_model="Result",
        output_key=response_key,
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
    "make_worker_step",
    "plan_step_count",
]
