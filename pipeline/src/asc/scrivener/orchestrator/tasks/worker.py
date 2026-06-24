"""Worker task factories used by orchestrator handlers."""

from __future__ import annotations

from asc.models.process.task import WorkerTask

from ..contracts import WORKER_EXECUTE_STEP


def make_worker_step(
    *,
    step_key: str,
    data_key: str,
) -> WorkerTask:
    """Create a Worker execute_step task for one materialized Step."""

    return WorkerTask(
        action=WORKER_EXECUTE_STEP,
        step_key=step_key,
        data_key=data_key,
    )


__all__ = ["make_worker_step"]
