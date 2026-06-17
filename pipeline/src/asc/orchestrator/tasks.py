"""Task factories and task-loading helpers for the orchestrator.

The cursor is deliberately small. It stores identity and call/plan keys only.
Step progress is derived from completed task records returned to the orchestrator;
the cursor does not carry a current task key.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from asc.models.process.loader import load_key
from asc.models.process.task import ScrivenerTask, WorkerTask

from .errors import OrchestratorContractError


@dataclass(frozen=True, slots=True)
class RouteDecision:
    queue_name: str | None
    task: WorkerTask | ScrivenerTask | None
    reason: str


# ---------------------------------------------------------------------------
# Keys and JSON
# ---------------------------------------------------------------------------


def is_cursor_key(key: str) -> bool:
    """Return True when a queue token is a cursor key.

    Current runtime keys use ``kind:identity:suffix``.  A newly enqueued
    cursor is therefore ``cursor:<call_identity>:index``.  The old
    ``runtime:<identity>:cursor`` shape is still recognized only so the
    orchestrator can fail usefully during a migration.
    """
    text = required_text(key, "cursor_key")
    return text.startswith("cursor:") or text.endswith(":cursor")


def cursor_key_for(cursor: Any) -> str:
    for attr in ("key", "cursor_key"):
        value = getattr(cursor, attr, None)
        if isinstance(value, str) and value.strip() and is_cursor_key(value.strip()):
            return value.strip()

    identity = required_text(getattr(cursor, "identity", None), "cursor.identity")
    return f"cursor:{identity}:index"


def content_key(identity: str, task_number: int) -> str:
    if task_number < 1:
        raise OrchestratorContractError(f"invalid content task: {task_number}")
    return f"content:{identity}:{int(task_number)}"


def task_identity(call_identity: str, daemon: str, action: str, step_number: int = 0) -> str:
    """Return a unique Redis identity for a runtime task.

    Task models use RedisModel.key_for_identity(), so the model identity must
    identify the task, not merely the call. The original call id remains in
    call_identity for grouping and ledger lookup.
    """
    call_identity = required_text(call_identity, "call_identity")
    daemon = required_text(daemon, "daemon")
    action = required_text(action, "action")
    if step_number:
        return f"{call_identity}.{daemon}.{action}.{int(step_number)}"
    return f"{call_identity}.{daemon}.{action}"


def required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise OrchestratorContractError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise OrchestratorContractError(f"{field_name} must be non-empty")
    return text


def required_key(value: object, field_name: str) -> str:
    """Return a Redis key as text."""
    if value is None:
        raise OrchestratorContractError(f"{field_name} must be non-empty")
    text = str(value).strip()
    if not text:
        raise OrchestratorContractError(f"{field_name} must be non-empty")
    return text


def task_number_for(task: Any) -> int:
    """Return the task sequence number from the canonical field.

    The process task models use task_number.  During the job→task cleanup,
    older orchestrator code still read step_number in a few places; keep this
    helper local so we do not put compatibility fields back into the models.
    """

    value = getattr(task, "task_number", None)
    if value is None:
        value = getattr(task, "step_number", None)
    if value is None:
        raise OrchestratorContractError("task.task_number is required")
    return int(value)


def json_blob(value: Mapping[str, Any] | str | None) -> str:
    if value is None:
        return "{}"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Task loading
# ---------------------------------------------------------------------------


def load_task(task_key: str) -> WorkerTask | ScrivenerTask:
    key = required_text(task_key, "task_key")
    task = load_key(key)
    if isinstance(task, (WorkerTask, ScrivenerTask)):
        return task
    raise OrchestratorContractError(
        f"orchestrator expected runtime task key, got {type(task).__name__}: {key}"
    )


def runtime_task_key_for(task: WorkerTask | ScrivenerTask) -> str:
    """Return the Redis key for a runtime task without trusting save() output."""

    identity = required_text(getattr(task, "identity", None), "task.identity")
    kind = required_text(getattr(task, "kind", None), "task.kind")

    key_for_identity = getattr(task, "key_for_identity", None)
    if callable(key_for_identity):
        try:
            return required_key(key_for_identity(identity), "task.key_for_identity(identity)")
        except TypeError:
            return required_key(key_for_identity(), "task.key_for_identity()")

    return f"task:{identity}:{kind}"


def task_key_has_kind(key: str, kind: object) -> bool:
    """Return True when an ephemeral task key has the expected Redis kind.

    Task and outcome models now use message-style keys: ``kind:identity``.
    Do not inspect the identity tail for worker/scrivener routing; action and
    provenance live in the hash values, not in the queue contract.
    """

    expected = required_text(kind, "task.kind")
    return required_text(key, "task_key").split(":", 1)[0] == expected


def assert_task_key_for_queue(*, queue_name: str, task_key: str) -> str:
    """Validate a queue handoff using the key kind, not suffix-shaped identity text."""

    key = required_text(task_key, f"{queue_name}.task_key")

    if queue_name == "worker":
        if not task_key_has_kind(key, WorkerTask.kind):
            raise OrchestratorContractError(f"worker queue requires worker task key, got: {key}")
        return key

    if queue_name == "scrivener":
        if not task_key_has_kind(key, ScrivenerTask.kind):
            raise OrchestratorContractError(f"scrivener queue requires scrivener task key, got: {key}")
        return key

    if queue_name == "orchestrator":
        if is_cursor_key(key) or task_key_has_kind(key, WorkerTask.kind) or task_key_has_kind(key, ScrivenerTask.kind):
            return key
        raise OrchestratorContractError(f"orchestrator queue received unknown key: {key}")

    raise OrchestratorContractError(f"unknown queue name: {queue_name!r}")


# ---------------------------------------------------------------------------
# Plan helpers
# ---------------------------------------------------------------------------


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
        try:
            loaded = json.loads(steps_json)
        except json.JSONDecodeError as exc:
            raise OrchestratorContractError("plan.steps_json is invalid JSON") from exc
        if isinstance(loaded, list):
            return len(loaded)

    raise OrchestratorContractError("cannot determine plan step count")


def plan_args_for_step(plan: Any, step_number: int) -> Mapping[str, Any]:
    if hasattr(plan, "args_for_step"):
        args = plan.args_for_step(step_number)
        if not isinstance(args, Mapping):
            raise OrchestratorContractError("PlanRecord.args_for_step() must return a mapping")
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

    raise OrchestratorContractError(f"cannot load plan args for step {step_number}")


def step_engine_key(value: object, *, step_number: int) -> str:
    """Normalize a plan step engine selector to a plain runtime module key."""
    if isinstance(value, str):
        text = value.strip()
    elif isinstance(value, Mapping):
        raw = value.get("key") or value.get("slug") or value.get("name")
        text = str(raw).strip() if raw is not None else ""
    else:
        text = ""

    if not text:
        raise OrchestratorContractError(f"plan step {step_number} has no engine")

    return text.removeprefix("engines.").replace("-", "_")


def step_handler_key(args: Mapping[str, Any], *, step_number: int) -> str:
    value = args.get("handler") or args.get("script") or args.get("model")
    if isinstance(value, Mapping):
        value = value.get("key") or value.get("slug") or value.get("name")
    text = str(value or "").strip()
    if not text:
        raise OrchestratorContractError(f"plan step {step_number} has no handler/script/model")
    return text


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def make_scrivener_call_task(cursor: Any) -> ScrivenerTask:
    identity = required_text(getattr(cursor, "identity", None), "cursor.identity")
    call_key = required_text(getattr(cursor, "call_key", None), "cursor.call_key")
    return ScrivenerTask(
        identity=task_identity(identity, "scrivener", "write-call"),
        cursor_key=cursor_key_for(cursor),
        action="write_call",
        task_number=0,
        engine="scrivener",
        handler="write_call",
        input_model="Call",
        input_key=call_key,
        output_model="LedgerCallRow",
        output_key=call_key,
        args_json="{}",
    )


def make_worker_task(
    *,
    cursor: Any,
    plan: Any,
    step_number: int,
    input_key: str | None = None,
) -> WorkerTask:
    identity = required_text(getattr(cursor, "identity", None), "cursor.identity")
    args = plan_args_for_step(plan, step_number)

    engine = step_engine_key(args.get("engine"), step_number=step_number)
    handler = step_handler_key(args, step_number=step_number)

    actual_input_key = input_key
    if actual_input_key is None:
        actual_input_key = (
            getattr(cursor, "call_key") if step_number == 1 else content_key(identity, step_number - 1)
        )

    return WorkerTask(
        identity=task_identity(identity, "worker", "execute-step", step_number),
        cursor_key=cursor_key_for(cursor),
        action="execute_step",
        task_number=int(step_number),
        engine=engine,
        handler=handler,
        input_model="Call" if step_number == 1 else "Result",
        input_key=required_text(actual_input_key, "worker.input_key"),
        output_model="Result",
        output_key=content_key(identity, step_number),
        args_json=json_blob(args),
    )


def make_scrivener_step_task(*, cursor: Any, worker_task: WorkerTask) -> ScrivenerTask:
    identity = required_text(getattr(cursor, "identity", None), "cursor.identity")
    step_number = task_number_for(worker_task)
    return ScrivenerTask(
        identity=task_identity(identity, "scrivener", "write-step", step_number),
        cursor_key=cursor_key_for(cursor),
        action="write_step",
        task_number=step_number,
        engine="scrivener",
        handler="write_step",
        input_model=worker_task.output_model,
        input_key=worker_task.output_key,
        output_model="LedgerStepRow",
        output_key=worker_task.output_key,
        args_json="{}",
    )


def make_scrivener_result_task(*, cursor: Any, previous_task: ScrivenerTask) -> ScrivenerTask:
    identity = required_text(getattr(cursor, "identity", None), "cursor.identity")
    return ScrivenerTask(
        identity=task_identity(identity, "scrivener", "write-result"),
        cursor_key=cursor_key_for(cursor),
        action="write_result",
        task_number=task_number_for(previous_task),
        engine="scrivener",
        handler="write_result",
        input_model=previous_task.input_model,
        input_key=previous_task.input_key,
        output_model="LedgerResultRow",
        output_key=previous_task.input_key,
        args_json="{}",
    )


__all__ = [
    "RouteDecision",
    "assert_task_key_for_queue",
    "content_key",
    "cursor_key_for",
    "load_task",
    "make_scrivener_call_task",
    "make_scrivener_result_task",
    "make_scrivener_step_task",
    "make_worker_task",
    "plan_step_count",
    "is_cursor_key",
    "runtime_task_key_for",
    "task_identity",
    "task_key_has_kind",
    "task_number_for",
]
