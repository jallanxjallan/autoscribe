"""Worker execution boundary.

The worker queue carries a WorkerTask key. The task is the custody/envelope
record and stays on the worker side. The engine receives only the runtime input
content, the Step, and the source CallRecord.

The worker does not post worker results to the orchestrator. It materializes the
result/failure artifact in Redis. The orchestrator discovers that deterministic
artifact key when it next inspects the active call index.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from asc.models.control.step import Step
from asc.models.process.call import CallRecord
from asc.models.process.result import Failure, Response, Result, Retrieval, Transform
from asc.models.process.task import WorkerTask
from asc.redis.key import RedisKey
from asc.worker.loader import load_engine_call
from asc.worker.runtime_io import load_runtime_input


RESULT_TYPES = (Response, Transform, Retrieval, Failure)
SUCCESS_TYPES = (Response, Transform, Retrieval)


@dataclass(frozen=True, slots=True)
class WorkerResult:
    processed: int
    task_key: str
    artifact_key: str
    failure_key: str | None = None


class WorkerExecutor:
    def execute(self, task: WorkerTask, task_key: str) -> WorkerResult:
        step = Step.load(task.step_key)
        call = _load_call_for_task(task)
        content = load_runtime_input(task.data_key)
        engine_call = load_engine_call(step.engine)

        try:
            artifact = engine_call(content=content, step=step, call=call)
            _validate_engine_artifact(
                artifact=artifact,
                task=task,
                step=step,
                call=call,
            )
            artifact_key = _save_engine_artifact(artifact=artifact, task=task, step=step)
        except Exception as exc:
            artifact_key = _save_runtime_failure(
                task=task,
                task_key=task_key,
                step=step,
                exc=exc,
            )
            return WorkerResult(
                processed=1,
                task_key=task_key,
                artifact_key=artifact_key,
                failure_key=artifact_key,
            )

        return WorkerResult(
            processed=1,
            task_key=task_key,
            artifact_key=artifact_key,
            failure_key=artifact_key if isinstance(artifact, Failure) else None,
        )


def _load_call_for_task(task: WorkerTask) -> CallRecord:
    call_identity = RedisKey(task.data_key).identity
    call_key = RedisKey(kind="call", identity=call_identity, suffix="record")
    return CallRecord.load(call_key.raw_key)


def _validate_engine_artifact(
    *,
    artifact: object,
    task: WorkerTask,
    step: Step,
    call: CallRecord,
) -> None:
    if not isinstance(artifact, RESULT_TYPES):
        raise TypeError(
            f"engine {step.engine!r} returned {type(artifact).__name__}; "
            "expected instantiated Response, Transform, Retrieval, or Failure"
        )

    if artifact.identity != call.identity:
        raise ValueError(
            "engine artifact identity does not match call identity: "
            f"artifact={artifact.identity!r} call={call.identity!r}"
        )

    if _artifact_suffix(artifact) != str(step.step_number):
        raise ValueError(
            "engine artifact suffix does not match step number: "
            f"artifact={_artifact_suffix(artifact)!r} step={step.step_number!r}"
        )

    expected_key = _expected_key_for_artifact(artifact=artifact, task=task, step=step)
    expected = RedisKey(expected_key)
    if expected.identity != artifact.identity:
        raise ValueError(
            "engine artifact identity does not match expected key identity: "
            f"artifact={artifact.identity!r} expected={expected.raw_key!r}"
        )
    if expected.suffix != _artifact_suffix(artifact):
        raise ValueError(
            "engine artifact suffix does not match expected key suffix: "
            f"artifact={_artifact_suffix(artifact)!r} expected={expected.raw_key!r}"
        )
    if expected.kind != _artifact_kind(artifact):
        raise ValueError(
            "engine artifact kind does not match expected key kind: "
            f"artifact={_artifact_kind(artifact)!r} expected={expected.raw_key!r}"
        )


def _save_engine_artifact(*, artifact: Result | Failure, task: WorkerTask, step: Step) -> str:
    expected_key = _expected_key_for_artifact(artifact=artifact, task=task, step=step)
    saved_key = artifact.save()
    if saved_key != expected_key:
        raise ValueError(
            "worker saved unexpected artifact key: "
            f"saved={saved_key!r} expected={expected_key!r}"
        )
    return saved_key


def _expected_key_for_artifact(*, artifact: Result | Failure, task: WorkerTask, step: Step) -> str:
    if isinstance(artifact, Failure):
        return _failure_key_for_task(task=task, step=step)
    if isinstance(artifact, SUCCESS_TYPES):
        return task.expected_key
    raise TypeError(f"unsupported worker artifact type: {type(artifact).__name__}")


def _save_runtime_failure(
    *,
    task: WorkerTask,
    task_key: str,
    step: Step,
    exc: Exception,
) -> str:
    failure = _runtime_failure(
        task=task,
        task_key=task_key,
        step=step,
        exc=exc,
    )
    failure_key = _failure_key_for_task(task=task, step=step)
    saved_key = failure.save()
    if saved_key != failure_key:
        raise ValueError(
            "worker saved unexpected failure key: "
            f"saved={saved_key!r} expected={failure_key!r}"
        )
    return saved_key


def _runtime_failure(
    *,
    task: WorkerTask,
    task_key: str,
    step: Step,
    exc: Exception,
) -> Failure:
    step_number = str(step.step_number)

    raw_json = {
        "task_key": task_key,
        "task_identity": task.identity,
        "data_key": task.data_key,
        "step_key": task.step_key,
        "expected_key": task.expected_key,
        "failure_key": _failure_key_for_task(task=task, step=step),
        "step_number": step_number,
        "engine": step.engine,
        "error": str(exc),
        "error_type": type(exc).__name__,
        "boundary": "worker.runtime",
    }

    return Failure.model_validate(
        {
            "identity": RedisKey(task.data_key).identity,
            "suffix": step_number,
            "failure_type": "runtime",
            "content": str(exc),
            "failure_reason": type(exc).__name__,
            "raw_json": raw_json,
            "boundary": "worker.runtime",
        }
    )


def _failure_key_for_task(*, task: WorkerTask, step: Step) -> str:
    if task.failure_key:
        expected = RedisKey(task.failure_key)
        if expected.kind != "failure":
            raise ValueError(f"worker failure_key must be a failure key: {task.failure_key!r}")
        return expected.raw_key

    return RedisKey(
        kind="failure",
        identity=RedisKey(task.data_key).identity,
        suffix=step.step_number,
    ).raw_key


def _artifact_kind(artifact: Result | Failure) -> str:
    if isinstance(artifact, Response):
        return "response"
    if isinstance(artifact, Transform):
        return "transform"
    if isinstance(artifact, Retrieval):
        return "retrieval"
    if isinstance(artifact, Failure):
        return "failure"
    raise TypeError(f"unsupported worker artifact type: {type(artifact).__name__}")


def _artifact_suffix(artifact: Result | Failure) -> str:
    suffix = getattr(artifact, "artifact_suffix", None)
    if suffix in (None, ""):
        raise ValueError(f"artifact missing suffix: {type(artifact).__name__}")
    return str(suffix)


__all__ = ["WorkerExecutor", "WorkerResult"]
