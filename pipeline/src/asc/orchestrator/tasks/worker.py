"""Worker task factories used by orchestrator handlers."""

from __future__ import annotations

from asc.models.process.task import WorkerTask
from asc.redis.key import RedisKey

from ..contracts import WORKER_EXECUTE_STEP



def make_worker_step(
    *,
    step_key: str,
    data_key: str,
) -> WorkerTask:
    """Create a Worker execute_step task for one materialized Step."""

    step_key = _required_text(step_key, "step_key")
    data_key = _required_text(data_key, "data_key")

    return WorkerTask(
        identity=_task_identity(data_key=data_key, step_key=step_key),
        action=WORKER_EXECUTE_STEP,
        step_key=step_key,
        data_key=data_key,
    )


def _task_identity(*, data_key: str, step_key: str) -> str:
    data_identity = RedisKey(data_key).identity
    step_identity = RedisKey(step_key).identity
    return f"{data_identity}.worker.{WORKER_EXECUTE_STEP}.{step_identity}"


def _required_text(value: object, field_name: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    return text


__all__ = ["make_worker_step"]
