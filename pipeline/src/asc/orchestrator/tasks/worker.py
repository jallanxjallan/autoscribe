"""Worker task factories used by orchestrator handlers."""

from __future__ import annotations

from typing import Any

from asc.models.process.task import Task
from asc.redis.key import RedisKey

from ..contracts import WORKER_EXECUTE_STEP


WORKER_PACKAGE = "worker"


def make_worker_step(
    *,
    cursor_key: str,
    step_key: str,
    call_key: str,
    step_number: int,
    **extra: Any,
) -> Task:
    """Create a Worker ``execute_step`` task for one materialized Step.

    The compact task contract uses ``source_key`` as the canonical input key.
    ``step_key`` and ``input_key`` are also copied for the worker-side transition,
    but downstream code must be able to execute from ``source_key`` alone.
    """

    step_key = _required_text(step_key, "step_key")
    call_key = _required_text(call_key, "call_key")
    cursor_key = _required_text(cursor_key, "cursor_key")
    step_number = int(step_number)
    if step_number < 1:
        raise ValueError("step_number must be >= 1")

    data: dict[str, Any] = {
        "identity": _task_identity(call_key=call_key, step_number=step_number),
        "package": WORKER_PACKAGE,
        "action": WORKER_EXECUTE_STEP,
        "cursor_key": cursor_key,
        "call_key": call_key,
        # Canonical compact-task input field.
        "source_key": step_key,
        # Transitional aliases for worker validators/outcome copying.
        "input_key": step_key,
        "step_key": step_key,
        "task_number": step_number,
        "step_number": step_number,
        "args_json": "{}",
        "ttl_seconds": None,
    }
    data.update(extra)
    return Task(**data)


def _task_identity(*, call_key: str, step_number: int) -> str:
    return f"{RedisKey(call_key).identity}.worker.{WORKER_EXECUTE_STEP}.{step_number}"


def _required_text(value: object, field_name: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    return text


__all__ = ["WORKER_PACKAGE", "make_worker_step"]
