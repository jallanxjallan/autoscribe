"""Execute the canonical Runtime key claimed from the worker inbox."""

from __future__ import annotations

from dataclasses import dataclass

from asc.models.process.result import (
    Failure,
    Response,
    Retrieval,
    Transform,
    failure_location,
    record_failure,
)
from asc.models.process.runtime import Runtime
from asc.redis.key import RedisKey
from asc.worker.loader import load_engine_call
from asc.worker.runtime_io import build_engine_input


RESULT_TYPES = (Response, Transform, Retrieval, Failure)


@dataclass(frozen=True, slots=True)
class WorkerResult:
    processed: int
    runtime_key: str
    artifact_key: str
    failure_key: str | None = None
    action: str | None = None


class WorkerExecutor:
    def execute(self, runtime_key: str) -> WorkerResult:
        """Load and execute one claimed Runtime."""
        runtime: Runtime | None = None

        try:
            parsed_key = RedisKey(runtime_key)
            if parsed_key.kind != Runtime.kind:
                raise ValueError(
                    f"worker expected a runtime key, got {parsed_key.raw_key!r}"
                )

            runtime = Runtime.load(parsed_key)
            _validate_runtime_key(runtime=runtime, runtime_key=parsed_key)

            engine_input = build_engine_input(runtime)
            engine_call = load_engine_call(runtime.engine)
            artifact = engine_call(engine_input)

            _validate_engine_artifact(artifact=artifact, runtime=runtime)
            artifact_key = artifact.save()

        except Exception as exc:
            if runtime is None:
                process_identity = None
                try:
                    process_identity = RedisKey(runtime_key).identity
                except Exception:
                    pass
                failure_key = record_failure(
                    stage="worker.load_runtime",
                    exc=exc,
                    process_identity=process_identity,
                    runtime_key=runtime_key,
                )
                return WorkerResult(
                    processed=1,
                    runtime_key=runtime_key,
                    artifact_key=failure_key,
                    failure_key=failure_key,
                    action="load-runtime",
                )

            artifact = _runtime_failure(
                runtime=runtime,
                runtime_key=runtime_key,
                exc=exc,
            )
            artifact_key = artifact.save()
            return WorkerResult(
                processed=1,
                runtime_key=runtime_key,
                artifact_key=artifact_key,
                failure_key=artifact_key,
                action=runtime.engine_kind,
            )

        return WorkerResult(
            processed=1,
            runtime_key=runtime_key,
            artifact_key=artifact_key,
            failure_key=artifact_key if isinstance(artifact, Failure) else None,
            action=runtime.engine_kind,
        )


def _validate_runtime_key(*, runtime: Runtime, runtime_key: RedisKey) -> None:
    if runtime.identity != runtime_key.identity:
        raise ValueError(
            "runtime record identity does not match its Redis key: "
            f"record={runtime.identity!r} key={runtime_key.identity!r}"
        )
    if str(runtime.ordinal) != str(runtime_key.suffix):
        raise ValueError(
            "runtime record ordinal does not match its Redis key: "
            f"record={runtime.ordinal!r} key={runtime_key.suffix!r}"
        )


def _validate_engine_artifact(*, artifact: object, runtime: Runtime) -> None:
    if not isinstance(artifact, RESULT_TYPES):
        raise TypeError(
            f"engine {runtime.engine!r} returned {type(artifact).__name__}; "
            "expected instantiated Response, Transform, Retrieval, or Failure"
        )

    if artifact.identity != runtime.identity:
        raise ValueError(
            "engine artifact identity does not match runtime identity: "
            f"artifact={artifact.identity!r} runtime={runtime.identity!r}"
        )

    if str(artifact.ordinal) != str(runtime.ordinal):
        raise ValueError(
            "engine artifact ordinal does not match runtime ordinal: "
            f"artifact={artifact.ordinal!r} runtime={runtime.ordinal!r}"
        )


def _runtime_failure(
    *,
    runtime: Runtime,
    runtime_key: str,
    exc: Exception,
) -> Failure:
    return Failure.model_validate(
        {
            "identity": runtime.identity,
            "ordinal": runtime.ordinal,
            "failure_type": "runtime",
            "content": str(exc),
            "failure_reason": type(exc).__name__,
            "raw_json": {
                "runtime_key": runtime_key,
                "location": failure_location(exc),
                "runtime_identity": runtime.identity,
                "plan_identity": runtime.plan_identity,
                "ordinal": runtime.ordinal,
                "total_steps": runtime.total_steps,
                "engine_kind": runtime.engine_kind,
                "engine": runtime.engine,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "boundary": "worker.runtime",
            },
            "boundary": "worker.runtime",
            "location": failure_location(exc),
            "stage": "worker.runtime",
        }
    )


__all__ = ["WorkerExecutor", "WorkerResult"]
