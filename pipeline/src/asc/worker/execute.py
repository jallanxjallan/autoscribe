"""Worker execution boundary.

The worker queue carries a WorkerTask key. The task is the local custody record
for claiming work. It stays inside the worker.

Runtime execution loads:

- Step from WorkerTask.step_key
- current content from WorkerTask.data_key
- source CallRecord from the identity embedded in WorkerTask.data_key

The registered engine receives only content, step, and call. It returns an
instantiated runtime artifact model. The worker validates the artifact custody
coordinates and materializes it in Redis. It does not post anything to the
orchestrator; materialized Redis artifacts are the signal the orchestrator
will discover during its active-call polling loop.
"""

from __future__ import annotations

from dataclasses import dataclass

from asc.models.process.call import CallRecord
from asc.models.process.result import Failure, Response, Result, Retrieval, Transform
from asc.models.control.step import Step
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
        content = load_runtime_input(task.data_key)
        call = _load_call_for_data_key(task.data_key)
        engine_call = load_engine_call(step.engine)

        try:
            artifact = engine_call(content=content, step=step, call=call)
            _validate_engine_artifact(
                artifact=artifact,
                task=task,
                step=step,
                call=call,
            )
            artifact_key = artifact.save()
        except Exception as exc:
            artifact = _runtime_failure(
                task=task,
                task_key=task_key,
                step=step,
                call_identity=RedisKey(task.data_key).identity,
                exc=exc,
            )
            artifact_key = artifact.save()
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


def _load_call_for_data_key(data_key: str) -> CallRecord:
    call_key = RedisKey(
        kind="call",
        identity=RedisKey(data_key).identity,
        suffix="record",
    )
    return CallRecord.load(call_key)


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

    expected_identity = call.identity
    actual_identity = str(getattr(artifact, "identity", "")).strip()
    if actual_identity != expected_identity:
        raise ValueError(
            "engine artifact identity does not match source call identity: "
            f"artifact={actual_identity!r} call={expected_identity!r}"
        )

    expected_suffix = _step_number(step)
    actual_suffix = str(getattr(artifact, "result_suffix", getattr(artifact, "suffix", ""))).strip()
    if actual_suffix != expected_suffix:
        raise ValueError(
            "engine artifact suffix does not match step number: "
            f"artifact={actual_suffix!r} step={expected_suffix!r}"
        )

    if isinstance(artifact, SUCCESS_TYPES):
        _validate_success_kind_matches_task(artifact=artifact, task=task)


def _validate_success_kind_matches_task(*, artifact: Result, task: WorkerTask) -> None:
    expected_key = _optional_task_text(task, "expected_key")
    if not expected_key:
        return

    expected = RedisKey(expected_key)
    if expected.kind != artifact.kind:
        raise ValueError(
            "engine artifact kind does not match task expected_key: "
            f"artifact_kind={artifact.kind!r} expected_key={expected.raw_key!r}"
        )

    if expected.identity != artifact.identity or str(expected.suffix) != str(getattr(artifact, "result_suffix", "")):
        raise ValueError(
            "engine artifact key does not match task expected_key: "
            f"artifact_key={artifact.raw_key!r} expected_key={expected.raw_key!r}"
        )


def _runtime_failure(
    *,
    task: WorkerTask,
    task_key: str,
    step: Step,
    call_identity: str,
    exc: Exception,
) -> Failure:
    step_number = _step_number(step)

    return Failure.model_validate(
        {
            "identity": call_identity,
            "suffix": step_number,
            "failure_type": "runtime",
            "content": str(exc),
            "failure_reason": type(exc).__name__,
            "raw_json": {
                "task_key": task_key,
                "task_identity": task.identity,
                "data_key": task.data_key,
                "step_key": task.step_key,
                "expected_key": _optional_task_text(task, "expected_key") or "",
                "failure_key": _optional_task_text(task, "failure_key") or "",
                "step_number": step_number,
                "engine": step.engine,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "boundary": "worker.runtime",
            },
            "boundary": "worker.runtime",
        }
    )


def _step_number(step: Step) -> str:
    value = getattr(step, "step_number", None)
    if value in (None, ""):
        raise ValueError("step.step_number must not be empty")
    return str(value)


def _optional_task_text(task: WorkerTask, name: str) -> str | None:
    value = getattr(task, name, None)
    if value in (None, ""):
        return None
    return str(value).strip() or None


__all__ = ["WorkerExecutor", "WorkerResult"]
