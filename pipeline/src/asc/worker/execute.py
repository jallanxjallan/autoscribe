"""Worker execution boundary.

The worker queue carries a WorkerTask key. The task is the custody/envelope
record. The executable runtime instruction is the Step stored at
WorkerTask.step_key. The runtime input is the already-selected data record at
WorkerTask.data_key.

By the time the worker sees a Step, plan step definitions have already been
flattened into top-level fields. Do not parse args_json or reload/unpack the
Plan here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from asc.models.process.result import Failure
from asc.models.process.step import Step
from asc.models.process.task import WorkerTask
from asc.redis.key import RedisKey
from asc.worker.engines import load_engine_call
from asc.worker.runtime_io import load_runtime_content


@dataclass(frozen=True, slots=True)
class WorkerResult:
    processed: int
    task_key: str
    output_key: str


class WorkerExecutor:
    def execute(self, task: WorkerTask, task_key: str) -> WorkerResult:
        step = Step.load(task.step_key)

        try:
            input_content = load_runtime_content(task.data_key)
            engine_call = load_engine_call(step.executor, args=_step_args(step))
            outcome = engine_call(input_content)
        except Exception as exc:
            outcome = _failure_for_exception(
                task_key=task_key,
                task=task,
                step=step,
                exc=exc,
            )

        output_key = _output_key(data_key=task.data_key, outcome=outcome)
        outcome = _with_worker_fields(
            outcome,
            task=task,
            step=step,
            task_key=task_key,
            output_key=output_key,
        )
        outcome.save(output_key)

        return WorkerResult(
            processed=1,
            task_key=task_key,
            output_key=output_key,
        )


def _step_args(step: Step) -> dict[str, Any]:
    excluded = {
        "identity",
        "suffix",
        "call_key",
        "step_number",
        "executor",
        "action",
        "instructions_json",
        "args_json",
        "ttl_seconds",
        "created_at",
        "updated_at",
    }

    return {
        name: value
        for name, value in step.model_dump(mode="python").items()
        if name not in excluded and value not in (None, "")
    }


def _output_key(*, data_key: str, outcome: object) -> str:
    kind = "failure" if isinstance(outcome, Failure) else "response"
    identity = RedisKey(data_key).identity
    return str(RedisKey(kind=kind, identity=identity))


def _failure_for_exception(
    *,
    task_key: str,
    task: WorkerTask,
    step: Step,
    exc: Exception,
) -> Failure:
    identity = RedisKey(task.data_key).identity

    return Failure(
        identity=identity,
        content=str(exc),
        failure_reason=type(exc).__name__,
        raw_json={
            "task_key": task_key,
            "task_identity": task.identity,
            "step_key": task.step_key,
            "data_key": task.data_key,
            "step_number": step.step_number,
            "executor": step.executor,
            "action": step.action,
            "error": str(exc),
            "error_type": type(exc).__name__,
            "worker_boundary": "execute",
        },
    )


def _with_worker_fields(
    outcome: object,
    *,
    task: WorkerTask,
    step: Step,
    task_key: str,
    output_key: str,
) -> object:
    return outcome.model_copy(
        update={
            "identity": RedisKey(output_key).identity,
            "task_key": task_key,
            "task_identity": task.identity,
            "step_key": task.step_key,
            "data_key": task.data_key,
            "step_number": step.step_number,
            "executor": step.executor,
            "action": step.action,
        }
    )


__all__ = ["WorkerExecutor", "WorkerResult"]
