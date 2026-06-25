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

from asc.models.process.result import Failure, Result
from asc.redis.key import RedisKey
from asc.models.process.step import Step
from asc.models.process.task import Outcome, WorkerTask
from asc.worker.engines import load_engine_run
from asc.worker.runtime_io import load_runtime_content


@dataclass(frozen=True, slots=True)
class WorkerResult:
    processed: int
    task_key: str
    output_key: str
    outcome_key: str


class WorkerExecutor:
    def execute(self, task: WorkerTask, task_key: str) -> WorkerResult:
        step: Step | None = None

        try:
            step = Step.load(task.step_key)
            input_content = load_runtime_content(task.data_key)
            engine_run = load_engine_run(step.engine, args=_step_args(step))
            output = engine_run(input_content)
            result = Result.from_worker_output(output, task=task, step=step, task_key=task_key)
        except Exception as exc:
            result = _failure_for_exception(
                task=task,
                task_key=task_key,
                step=step,
                exc=exc,
            )

        identity = _result_identity(task)
        suffix = _result_suffix(task=task, step=step)
        output_key = _save_result(result=result, identity=identity, suffix=suffix)
        outcome_key = _save_outcome(task=task, output_key=output_key, result=result)

        return WorkerResult(
            processed=1,
            task_key=task_key,
            output_key=output_key,
            outcome_key=outcome_key,
        )


def _save_outcome(
    *,
    task: WorkerTask,
    output_key: str,
    result: Result | Failure,
) -> str:
    if isinstance(result, Failure):
        outcome = Outcome.failure(task=task, message=output_key)
    else:
        outcome = Outcome.success(task=task, message=output_key)

    return outcome.save()


def _failure_for_exception(
    *,
    task: WorkerTask,
    task_key: str,
    step: Step | None,
    exc: Exception,
) -> Failure:
    raw_json = {
        "task_key": task_key,
        "task_identity": task.identity,
        "data_key": task.data_key,
        "step_key": task.step_key,
        "step_number": _result_suffix(task=task, step=step),
        "error": str(exc),
        "error_type": type(exc).__name__,
        "boundary": "worker.execute",
    }

    return Failure.model_validate(
        {
            "identity": _result_identity(task),
            "failure_type": "internal",
            "content": str(exc),
            "failure_reason": type(exc).__name__,
            "raw_json": raw_json,
            "task_key": task_key,
            "task_identity": task.identity,
            "data_key": task.data_key,
            "step_key": task.step_key,
            "step_number": _result_suffix(task=task, step=step),
            "boundary": "worker.execute",
        }
    )


def _save_result(*, result: Result | Failure, identity: str, suffix: str) -> str:
    try:
        return result.save(identity=identity, suffix=suffix)
    except TypeError:
        output_key = _output_key(result=result, identity=identity, suffix=suffix)
        return result.save(output_key)


def _output_key(*, result: Result | Failure, identity: str, suffix: str) -> str:
    output_key_for = getattr(result, "output_key_for", None)
    if callable(output_key_for):
        return str(output_key_for(identity=identity, suffix=suffix))

    return str(RedisKey(kind=result.kind, identity=identity, suffix=suffix))


def _result_identity(task: WorkerTask) -> str:
    return RedisKey(task.data_key).identity


def _result_suffix(*, task: WorkerTask, step: Step | None) -> str:
    if step is not None:
        for name in ("step_number", "number"):
            value = getattr(step, name, None)
            if value not in (None, ""):
                return str(value)

    suffix = RedisKey(task.step_key).suffix
    if not suffix:
        raise ValueError(f"worker task step_key has no step suffix: {task.step_key!r}")

    return str(suffix)


def _step_args(step: Step) -> dict[str, Any]:
    return {
        name: value
        for name, value in step.model_dump(mode="python").items()
        if value not in (None, "")
    }


__all__ = ["WorkerExecutor", "WorkerResult"]
