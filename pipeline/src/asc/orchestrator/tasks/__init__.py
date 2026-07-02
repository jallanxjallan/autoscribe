"""Task factories for daemon inbox messages."""

from asc.models.process.task import ScrivenerTask, WorkerTask
from .scrivener import (
    make_scrivener_call_completed,
    make_scrivener_call_failed,
    make_scrivener_write_call,
    make_scrivener_write_step,
)
from .worker import make_worker_step


def save_task(task: ScrivenerTask | WorkerTask) -> str:
    """Save a concrete daemon task and return its Redis key."""

    return str(task.save())


__all__ = [
    "make_scrivener_call_completed",
    "make_scrivener_call_failed",
    "make_scrivener_write_call",
    "make_scrivener_write_step",
    "make_worker_step",
    "save_task",
]
