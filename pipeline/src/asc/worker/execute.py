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

from asc.models.process.result import Failure, Response, Result, Retrieval, Transform
from asc.models.process.step import Step
from asc.models.process.task import Outcome, WorkerTask
from asc.redis.key import RedisKey
from asc.worker.engines import load_engine_run, normalize_engine_kind
from asc.worker.runtime_io import load_runtime_content


@dataclass(frozen=True, slots=True)
class WorkerResult:
    processed: int
    task_key: str
    output_key: str
    outcome_key: str


class WorkerExecutor:
    def execute(self, task: WorkerTask, task_key: str) -> WorkerResult:
        step = Step.load(task.step_key)
        input_content = load_runtime_content(task.data_key)
        engine_run = load_engine_run(step.engine, args=_step_args(step))
        result_class = _result_class_for_step(step)

        identity = _result_identity(task)
        suffix = _result_suffix(task=task, step=step)

        try:
            output = engine_run(input_content)
        except Exception as exc:
            result: Result | Failure = _runtime_failure(
                task=task,
                task_key=task_key,
                step=step,
                exc=exc,
            )
        else:
            result = _result_from_engine_output(
                output=output,
                result_class=result_class,
                identity=identity,
            )

        output_key = result.save(identity=identity, suffix=suffix)
        outcome_key = _save_outcome(task=task, output_key=output_key, result=result)

        return WorkerResult(
            processed=1,
            task_key=task_key,
            output_key=output_key,
            outcome_key=outcome_key,
        )


def _result_from_engine_output(
    *,
    output: object,
    result_class: type[Result],
    identity: str,
) -> Result | Failure:
    if isinstance(output, (Result, Failure)):
        return output

    payload = _payload_from_output(output)

    return result_class(
        identity=identity,
        content=payload["content"],
        raw_json=payload["raw_json"],
    )


def _result_class_for_step(step: Step) -> type[Result]:
    engine = normalize_engine_kind(step.engine)

    if engine == "llm":
        return Response

    if engine == "script":
        return Transform

    if engine == "rag":
        return Retrieval

    raise ValueError(f"unsupported worker step engine: {step.engine!r}")


def _payload_from_output(output: object) -> dict[str, object]:
    if isinstance(output, dict):
        content = output.get("content")
        if content is None:
            content = output.get("text")
        if content is None:
            content = str(output)

        return {
            "content": content,
            "raw_json": output,
        }

    if isinstance(output, bytes):
        text = output.decode("utf-8")
        return {
            "content": text,
            "raw_json": {"content": text},
        }

    return {
        "content": "" if output is None else str(output),
        "raw_json": {"content": output},
    }


def _runtime_failure(
    *,
    task: WorkerTask,
    task_key: str,
    step: Step,
    exc: Exception,
) -> Failure:
    step_number = _result_suffix(task=task, step=step)

    raw_json = {
        "task_key": task_key,
        "task_identity": task.identity,
        "data_key": task.data_key,
        "step_key": task.step_key,
        "step_number": step_number,
        "engine": step.engine,
        "error": str(exc),
        "error_type": type(exc).__name__,
        "boundary": "worker.runtime",
    }

    return Failure.model_validate(
        {
            "identity": _result_identity(task),
            "failure_type": "runtime",
            "content": str(exc),
            "failure_reason": type(exc).__name__,
            "raw_json": raw_json,
            "boundary": "worker.runtime",
        }
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


def _result_identity(task: WorkerTask) -> str:
    return RedisKey(task.data_key).identity


def _result_suffix(*, task: WorkerTask, step: Step) -> str:
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