from __future__ import annotations

import time
from typing import Any

from asc.models.process.scrivener import ScrivenerFailure, ScrivenerResult


def job_value(job: Any, name: str, default: Any = "") -> Any:
    if isinstance(job, dict):
        return job.get(name, default)
    return getattr(job, name, default)


def job_identity(job: Any) -> str:
    value = job_value(job, "identity", "")
    if not value:
        value = job_value(job, "call_identity", "")
    if not value:
        raise ValueError("scrivener job missing identity")
    return str(value)


def job_action(job: Any) -> str:
    value = job_value(job, "action", "")
    if not value:
        value = job_value(job, "handler", "")
    if not value:
        raise ValueError("scrivener job missing action")
    return str(value)


def job_ledger_table(job: Any) -> str:
    value = job_value(job, "ledger_table", "")
    if value:
        return str(value)

    action = job_action(job)
    if action.startswith("call") or action == "write_call":
        return "calls"
    if action.startswith("step") or action == "write_step":
        return "steps"
    if action.startswith("result") or action in {"call_completed", "write_result"}:
        return "results"
    if action.startswith("export") or action == "write_export":
        return "exports"
    return ""


def job_key(job: Any) -> str:
    value = job_value(job, "redis_key", "") or job_value(job, "job_key", "")
    return str(value or "")


def now_ns() -> int:
    return time.time_ns()


def scrivener_result(job: Any) -> ScrivenerResult:
    return ScrivenerResult(
        identity=job_identity(job),
        action=job_action(job),
        job_key=job_key(job),
        ledger_table=job_ledger_table(job),
        created_at=now_ns(),
    )


def scrivener_failure(job: Any, exc: BaseException) -> ScrivenerFailure:
    return ScrivenerFailure(
        identity=job_identity(job),
        action=job_action(job),
        job_key=job_key(job),
        ledger_table=job_ledger_table(job),
        fail_message=str(exc),
        failure_reason=exc.__class__.__name__,
        raw_error_json={
            "module": exc.__class__.__module__,
            "class": exc.__class__.__name__,
        },
        created_at=now_ns(),
    )


def save_outcome(outcome: ScrivenerResult | ScrivenerFailure) -> str:
    outcome.save()
    return str(outcome.redis_key)


__all__ = [
    "job_action",
    "job_identity",
    "job_key",
    "job_ledger_table",
    "save_outcome",
    "scrivener_failure",
    "scrivener_result",
]
