"""Job factories and job-loading helpers for the orchestrator.

The cursor is deliberately small. It stores identity and call/plan keys.
Step progress is derived from completed job records returned to the orchestrator.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from asc.models.process.task import WorkerTask, ScrivenerTask, TaskStatus
from asc.models.process.loader import load_key

from .errors import OrchestratorContractError


@dataclass(frozen=True, slots=True)
class RouteDecision:
    queue_name: str | None
    task: WorkerTask | ScrivenerTask | None
    reason: str


# ---------------------------------------------------------------------------
# Keys and JSON
# ---------------------------------------------------------------------------


def cursor_key_for(cursor: Any) -> str:
    identity = required_text(getattr(cursor, "identity", None), "cursor.identity")
    return f"runtime:{identity}:cursor"


def current_job_key(cursor: Any) -> str:
    """Return the current job key from the canonical cursor field.

    ``current_job`` is the field consumed by workers and scrivener. The older
    ``current_job_key`` name is read only as a defensive bridge for cursors that
    may already be sitting in Redis from an earlier run.
    """
    value = getattr(cursor, "current_job", None)
    if value in (None, ""):
        value = getattr(cursor, "current_job_key", "")
    if value is None:
        return ""
    return str(value).strip()


def content_key(identity: str, step_number: int) -> str:
    if step_number < 1:
        raise OrchestratorContractError(f"invalid content step: {step_number}")
    return f"runtime:{identity}:content.{step_number}"


def job_identity(call_identity: str, daemon: str, action: str, step_number: int = 0) -> str:
    """Return a unique Redis identity for a runtime job.

    Job models use RedisModel.key_for_identity(), so the model identity must
    identify the job, not merely the call. The original call id remains in
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
    """Return a Redis key as text.

    Some Redis key helpers return key-like objects rather than raw strings.
    Model fields should still use required_text(); generated Redis keys use this.
    """
    if value is None:
        raise OrchestratorContractError(f"{field_name} must be non-empty")
    text = str(value).strip()
    if not text:
        raise OrchestratorContractError(f"{field_name} must be non-empty")
    return text


def json_blob(value: Mapping[str, Any] | str | None) -> str:
    if value is None:
        return "{}"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Job loading
# ---------------------------------------------------------------------------


def load_job(job_key: str) -> WorkerTask | ScrivenerTask:
    key = required_text(job_key, "job_key")
    job = load_key(key)
    if isinstance(job, (WorkerTask, ScrivenerTask)):
        return job
    raise OrchestratorContractError(
        f"orchestrator expected runtime job key, got {type(job).__name__}: {key}"
    )




def runtime_job_key_for(job: WorkerTask | ScrivenerTask) -> str:
    """Return the Redis key for a runtime job without trusting save() output.

    RedisModel.save() return values are not a queue contract. Queues must carry
    the persisted job key, so the orchestrator computes that key from the job
    model itself and only uses save() for persistence.
    """

    identity = required_text(getattr(job, "identity", None), "job.identity")
    kind = required_text(getattr(job, "kind", None), "job.kind")

    key_for_identity = getattr(job, "key_for_identity", None)
    if callable(key_for_identity):
        try:
            return required_key(key_for_identity(identity), "job.key_for_identity(identity)")
        except TypeError:
            # Some RedisModel implementations expose key_for_identity as an
            # instance method taking no arguments. Support that shape too, but
            # do not rely on save() returning the key.
            return required_key(key_for_identity(), "job.key_for_identity()")

    domain = str(getattr(job, "domain", "runtime") or "runtime").strip()
    return f"{domain}:{identity}:{kind}"


def assert_job_key_for_queue(*, queue_name: str, job_key: str) -> str:
    """Validate that a queue handoff is a job key, not a cursor key."""

    key = required_text(job_key, f"{queue_name}.job_key")
    if key.endswith(":cursor") or ":cursor" in key:
        raise OrchestratorContractError(
            f"refusing to enqueue cursor key on {queue_name} queue: {key}"
        )

    if queue_name == "worker" and not key.endswith(f":{WorkerJobRecord.kind}"):
        raise OrchestratorContractError(f"worker queue requires worker job key, got: {key}")

    if queue_name == "scrivener" and not key.endswith(f":{ScrivenerTask.kind}"):
        raise OrchestratorContractError(f"scrivener queue requires ledger job key, got: {key}")

    if queue_name == "orchestrator" and not (
        key.endswith(":cursor")
        or key.endswith(f":{WorkerJobRecord.kind}")
        or key.endswith(f":{ScrivenerTask.kind}")
    ):
        raise OrchestratorContractError(f"orchestrator queue received unknown key: {key}")

    return key


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


def make_ledger_call_job(cursor: Any) -> LedgerJobRecord:
    identity = required_text(getattr(cursor, "identity", None), "cursor.identity")
    call_key = required_text(getattr(cursor, "call_key", None), "cursor.call_key")
    return LedgerJobRecord(
        identity=job_identity(identity, "ledger", "write-call"),
        call_identity=identity,
        cursor_key=cursor_key_for(cursor),
        action="write_call",
        step_number=0,
        engine="ledger",
        handler="write_call",
        input_model="Call",
        input_key=call_key,
        output_model="LedgerCallRow",
        output_key=call_key,
        args_json="{}",
    )


def make_worker_job(
    *,
    cursor: Any,
    plan: Any,
    step_number: int,
    input_key: str | None = None,
) -> WorkerJobRecord:
    identity = required_text(getattr(cursor, "identity", None), "cursor.identity")
    args = plan_args_for_step(plan, step_number)

    engine = step_engine_key(args.get("engine"), step_number=step_number)
    handler = step_handler_key(args, step_number=step_number)

    actual_input_key = input_key
    if actual_input_key is None:
        actual_input_key = getattr(cursor, "call_key") if step_number == 1 else content_key(identity, step_number - 1)

    return WorkerJobRecord(
        identity=job_identity(identity, "worker", "execute-step", step_number),
        call_identity=identity,
        cursor_key=cursor_key_for(cursor),
        action="execute_step",
        step_number=int(step_number),
        engine=engine,
        handler=handler,
        input_model="Call" if step_number == 1 else "Result",
        input_key=required_text(actual_input_key, "worker.input_key"),
        output_model="Result",
        output_key=content_key(identity, step_number),
        args_json=json_blob(args),
    )


def make_ledger_step_job(*, cursor: Any, worker_job: WorkerJobRecord) -> LedgerJobRecord:
    identity = required_text(getattr(cursor, "identity", None), "cursor.identity")
    step_number = int(worker_job.step_number)
    return LedgerJobRecord(
        identity=job_identity(identity, "ledger", "write-step", step_number),
        call_identity=identity,
        cursor_key=cursor_key_for(cursor),
        action="write_step",
        step_number=step_number,
        engine="ledger",
        handler="write_step",
        input_model=worker_job.output_model,
        input_key=worker_job.output_key,
        output_model="LedgerStepRow",
        output_key=worker_job.output_key,
        args_json="{}",
    )


def make_ledger_result_job(*, cursor: Any, previous_job: LedgerJobRecord) -> LedgerJobRecord:
    identity = required_text(getattr(cursor, "identity", None), "cursor.identity")
    return LedgerJobRecord(
        identity=job_identity(identity, "ledger", "write-result"),
        call_identity=identity,
        cursor_key=cursor_key_for(cursor),
        action="write_result",
        step_number=int(previous_job.step_number),
        engine="ledger",
        handler="write_result",
        input_model=previous_job.input_model,
        input_key=previous_job.input_key,
        output_model="LedgerResultRow",
        output_key=previous_job.input_key,
        args_json="{}",
    )


__all__ = [
    "RouteDecision",
    "content_key",
    "cursor_key_for",
    "load_job",
    "make_ledger_call_job",
    "make_ledger_result_job",
    "make_ledger_step_job",
    "make_worker_job",
    "plan_step_count",
]
