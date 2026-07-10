"""Worker execution boundary.

The worker claims a WorkerTask, loads the persisted models needed for one step,
builds one immutable EngineInput object, and passes that object to the selected
engine.

The engine owns provider-specific formatting. The worker owns custody checks
and Redis materialization.
"""

from __future__ import annotations

from dataclasses import dataclass

from asc.models.control.step import Step
from asc.models.process.result import Failure, Response, Result, Retrieval, Transform
from asc.models.process.task import WorkerTask
from asc.redis.key import RedisKey
from asc.worker.loader import load_engine_call
from asc.worker.runtime_io import build_engine_input


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
        """Execute one claimed task and materialize a result or failure."""

        step: Step | None = None

        try:
            step = Step.load(task.step_key)
            engine_input = build_engine_input(
                data_key=task.data_key,
                step=step,
            )
            engine_call = load_engine_call(step.engine)

            artifact = engine_call(engine_input)

            _validate_engine_artifact(
                artifact=artifact,
                task=task,
                step=step,
                call_identity=engine_input.call.identity,
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


def _validate_engine_artifact(
    *,
    artifact: object,
    task: WorkerTask,
    step: Step,
    call_identity: str,
) -> None:
    if not isinstance(artifact, RESULT_TYPES):
        raise TypeError(
            f"engine {step.engine!r} returned {type(artifact).__name__}; "
            "expected instantiated Response, Transform, Retrieval, or Failure"
        )

    if artifact.identity != call_identity:
        raise ValueError(
            "engine artifact identity does not match source call identity: "
            f"artifact={artifact.identity!r} call={call_identity!r}"
        )

    expected_ordinal = str(step.ordinal)
    actual_ordinal = str(artifact.ordinal)

    if actual_ordinal != expected_ordinal:
        raise ValueError(
            "engine artifact ordinal does not match step ordinal: "
            f"artifact={actual_ordinal!r} step={expected_ordinal!r}"
        )

    if isinstance(artifact, SUCCESS_TYPES):
        _validate_success_key(artifact=artifact, task=task)


def _validate_success_key(*, artifact: Result, task: WorkerTask) -> None:
    expected = RedisKey(task.expected_key)

    if expected.kind != artifact.kind:
        raise ValueError(
            "engine artifact kind does not match task expected_key: "
            f"artifact_kind={artifact.kind!r} expected_key={expected.raw_key!r}"
        )

    if expected.identity != artifact.identity:
        raise ValueError(
            "engine artifact identity does not match task expected_key: "
            f"artifact={artifact.identity!r} expected={expected.identity!r}"
        )

    if str(expected.suffix) != str(artifact.ordinal):
        raise ValueError(
            "engine artifact ordinal does not match task expected_key: "
            f"artifact={artifact.ordinal!r} expected={expected.suffix!r}"
        )


def _runtime_failure(
    *,
    task: WorkerTask,
    task_key: str,
    step: Step | None,
    call_identity: str,
    exc: Exception,
) -> Failure:
    ordinal = _task_ordinal(task=task, step=step)
    engine = "" if step is None else step.engine

    return Failure.model_validate(
        {
            "identity": call_identity,
            "ordinal": ordinal,
            "failure_type": "runtime",
            "content": str(exc),
            "failure_reason": type(exc).__name__,
            "raw_json": {
                "task_key": task_key,
                "task_identity": task.identity,
                "data_key": task.data_key,
                "step_key": task.step_key,
                "expected_key": task.expected_key,
                "failure_key": task.failure_key,
                "ordinal": ordinal,
                "engine": engine,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "boundary": "worker.runtime",
            },
            "boundary": "worker.runtime",
        }
    )


def _task_ordinal(*, task: WorkerTask, step: Step | None) -> str:
    if step is not None:
        return str(step.ordinal)

    suffix = RedisKey(task.step_key).suffix
    if suffix in (None, ""):
        raise ValueError(f"worker task step_key has no ordinal: {task.step_key!r}")
    return str(suffix)


__all__ = ["WorkerExecutor", "WorkerResult"]
