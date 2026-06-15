"""Job factories and job-loading helpers for the orchestrator.

The cursor is now deliberately small. It stores identity, call/plan keys, and
``current_job_key`` only. Step progress is derived from the current job and
ledger/runtime artifacts, not from cursor step fields.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from asc.models.runtime.job import LedgerJobRecord, WorkerJobRecord

from .errors import OrchestratorContractError


@dataclass(frozen=True, slots=True)
class RouteDecision:
    queue_name: str | None
    job: WorkerJobRecord | LedgerJobRecord | None
    reason: str


# ---------------------------------------------------------------------------
# Keys and JSON
# ---------------------------------------------------------------------------


def cursor_key_for(cursor: Any) -> str:
    identity = required_text(getattr(cursor, "identity", None), "cursor.identity")
    return f"runtime:{identity}:cursor"


def current_job_key(cursor: Any) -> str:
    value = getattr(cursor, "current_job_key", "")
    if value is None:
        return ""
    return str(value).strip()


def content_key(identity: str, step_number: int) -> str:
    if step_number < 1:
        raise OrchestratorContractError(f"invalid content step: {step_number}")
    return f"runtime:{identity}:content.{step_number}"


def required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise OrchestratorContractError(f"{field_name} must be a string")
    text = value.strip()
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


def load_job(job_key: str) -> WorkerJobRecord | LedgerJobRecord:
    key = required_text(job_key, "job_key")
    kind = key.rsplit(":", 1)[-1]

    if kind == WorkerJobRecord.kind:
        return WorkerJobRecord.load(key)
    if kind == LedgerJobRecord.kind:
        return LedgerJobRecord.load(key)

    raise OrchestratorContractError(f"unknown runtime job kind in key: {key}")


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


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def make_ledger_call_job(cursor: Any) -> LedgerJobRecord:
    identity = required_text(getattr(cursor, "identity", None), "cursor.identity")
    call_key = required_text(getattr(cursor, "call_key", None), "cursor.call_key")
    return LedgerJobRecord(
        identity=identity,
        call_identity=identity,
        cursor_key=cursor_key_for(cursor),
        action="write_call",
        step_number=0,
        engine="ledger",
        handler="write_call",
        input_model="CallRecord",
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

    engine = str(args.get("engine") or "").strip()
    handler = str(args.get("handler") or args.get("script") or args.get("model") or "").strip()
    if not engine:
        raise OrchestratorContractError(f"plan step {step_number} has no engine")
    if not handler:
        raise OrchestratorContractError(f"plan step {step_number} has no handler/script/model")

    actual_input_key = input_key
    if actual_input_key is None:
        actual_input_key = getattr(cursor, "call_key") if step_number == 1 else content_key(identity, step_number - 1)

    return WorkerJobRecord(
        identity=identity,
        call_identity=identity,
        cursor_key=cursor_key_for(cursor),
        action="execute_step",
        step_number=int(step_number),
        engine=engine,
        handler=handler,
        input_model="CallRecord" if step_number == 1 else "ResponseRecord",
        input_key=required_text(actual_input_key, "worker.input_key"),
        output_model="ResponseRecord",
        output_key=content_key(identity, step_number),
        args_json=json_blob(args),
    )


def make_ledger_step_job(*, cursor: Any, worker_job: WorkerJobRecord) -> LedgerJobRecord:
    identity = required_text(getattr(cursor, "identity", None), "cursor.identity")
    step_number = int(worker_job.step_number)
    return LedgerJobRecord(
        identity=identity,
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
        identity=identity,
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
    "current_job_key",
    "cursor_key_for",
    "load_job",
    "make_ledger_call_job",
    "make_ledger_result_job",
    "make_ledger_step_job",
    "make_worker_job",
    "plan_step_count",
]
