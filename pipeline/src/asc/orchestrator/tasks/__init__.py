"""Task factories for daemon inbox messages."""

from asc.models.process.task import ScrivenerTask, WorkerTask
from asc.redis.key import RedisKey
from asc.redis.primitives import hashes

from .scrivener import (
    make_scrivener_call_completed,
    make_scrivener_call_failed,
    make_scrivener_write_call,
    make_scrivener_write_step,
)
from .worker import make_worker_step


def save_task(task: ScrivenerTask | WorkerTask) -> str:
    """Save a task and persist expected artifact fields.

    Pydantic model configuration may not include future task fields yet. The
    factories attach expected_key/failure_key by model_copy(update=...), then
    this helper writes those fields directly to the saved task hash so queue
    managers can rely on them.
    """

    task_key = str(task.save())
    expected_key = _required_task_attr(task, "expected_key")
    hashes.hset(RedisKey(task_key), field="expected_key", value=expected_key)

    failure_key = _optional_task_attr(task, "failure_key")
    if failure_key is not None:
        hashes.hset(RedisKey(task_key), field="failure_key", value=failure_key)

    return task_key


def _required_task_attr(task: ScrivenerTask | WorkerTask, name: str) -> str:
    value = _optional_task_attr(task, name)
    if value is None:
        raise ValueError(f"task {name} must be non-empty: {task!r}")
    return value


def _optional_task_attr(task: ScrivenerTask | WorkerTask, name: str) -> str | None:
    value = getattr(task, name, None)
    text = "" if value is None else str(value).strip()
    return text or None


__all__ = [
    "make_scrivener_call_completed",
    "make_scrivener_call_failed",
    "make_scrivener_write_call",
    "make_scrivener_write_step",
    "make_worker_step",
    "save_task",
]
