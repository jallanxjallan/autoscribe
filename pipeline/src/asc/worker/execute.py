"""Worker execution boundary.

The worker queue carries a WorkerTask key. The task is the custody/envelope
record. The executable runtime instruction is the Step stored at
WorkerTask.step_key. The runtime input is the already-selected data record at
WorkerTask.data_key.

Workers no longer emit Outcome receipts. The task supplies the success artifact
key in expected_key. On success, the worker writes that exact artifact. Runtime
failures are still written as failure:<call_identity>:<step_number> so the
orchestrator can observe failure artifacts directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from asc.models.process.result import Failure, Response, Result, Retrieval, Transform
from asc.models.control.step import Step
from asc.models.process.task import WorkerTask
from asc.redis.key import RedisKey
from asc.worker.loader import load_engine_call
from asc.worker.runtime_io import load_runtime_input


@dataclass(frozen=True, slots=True)
class WorkerResult:
    processed: int
    task_key: str
    artifact_key: str
    failure_key: str | None = None


class WorkerExecutor:
    def execute(self, task: WorkerTask, task_key: str) -> WorkerResult:
        step = Step.load(task.step_key)
        runtime_input = load_runtime_input(task.data_key)
        engine_call = load_engine_call(step.engine)
        expected_key = task.expected_key

        try:
            output = engine_call(step=step, content=runtime_input, task=task)
        except Exception as exc:
            failure_key = _save_runtime_failure(
                task=task,
                task_key=task_key,
                step=step,
                exc=exc,
            )
            return WorkerResult(
                processed=1,
                task_key=task_key,
                artifact_key=failure_key,
                failure_key=failure_key,
            )

        result = _result_from_engine_output(
            output=output,
            expected_key=expected_key,
            identity=RedisKey(expected_key).identity,
        )
        artifact_key = _save_result_at_expected_key(
            result=result,
            expected_key=expected_key,
        )

        return WorkerResult(
            processed=1,
            task_key=task_key,
            artifact_key=artifact_key,
        )


def _result_from_engine_output(
    *,
    output: object,
    expected_key: str,
    identity: str,
) -> Result | Failure:
    if isinstance(output, (Result, Failure)):
        return output

    payload = _payload_from_output(output)

    return _result_class_for_expected_key(expected_key)(
        identity=identity,
        content=payload["content"],
        raw_json=payload["raw_json"],
    )


def _result_class_for_expected_key(expected_key: str) -> type[Result]:
    kind = RedisKey(expected_key).kind

    if kind == "response":
        return Response

    if kind == "transform":
        return Transform

    if kind == "retrieval":
        return Retrieval

    raise ValueError(f"unsupported worker expected_key kind: {expected_key!r}")


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


def _save_result_at_expected_key(
    *,
    result: Result | Failure,
    expected_key: str,
) -> str:
    expected = RedisKey(expected_key)
    if expected.kind != _result_kind(result):
        raise ValueError(
            "worker result kind does not match task expected_key: "
            f"result_kind={_result_kind(result)!r} expected_key={expected.raw_key!r}"
        )

    saved_key = result.save(identity=expected.identity, suffix=expected.suffix)
    if str(saved_key) != expected.raw_key:
        raise ValueError(
            "worker saved unexpected artifact key: "
            f"saved={saved_key!r} expected={expected.raw_key!r}"
        )

    return str(saved_key)


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
    failure_key = _optional_task_text(task, "failure_key") or _default_failure_key(
        task=task,
        step=step,
    )
    expected = RedisKey(failure_key)
    if expected.kind != "failure":
        raise ValueError(f"worker failure_key must be a failure key: {failure_key!r}")

    saved_key = failure.save(identity=expected.identity, suffix=expected.suffix)
    if str(saved_key) != expected.raw_key:
        raise ValueError(
            "worker saved unexpected failure key: "
            f"saved={saved_key!r} expected={expected.raw_key!r}"
        )

    return str(saved_key)


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
        "expected_key": _optional_task_text(task, "expected_key") or "",
        "failure_key": _optional_task_text(task, "failure_key") or "",
        "step_number": step_number,
        "engine": step.engine,
        "error": str(exc),
        "error_type": type(exc).__name__,
        "boundary": "worker.runtime",
    }

    return Failure.model_validate(
        {
            "identity": RedisKey(task.data_key).identity,
            "failure_type": "runtime",
            "content": str(exc),
            "failure_reason": type(exc).__name__,
            "raw_json": raw_json,
            "boundary": "worker.runtime",
        }
    )


def _result_kind(result: Result | Failure) -> str:
    if isinstance(result, Failure):
        return "failure"
    if isinstance(result, Response):
        return "response"
    if isinstance(result, Transform):
        return "transform"
    if isinstance(result, Retrieval):
        return "retrieval"
    raise TypeError(f"unsupported worker result type: {type(result).__name__}")


def _result_suffix(*, task: WorkerTask, step: Step) -> str:
    for name in ("step_number", "number"):
        value = getattr(step, name, None)
        if value not in (None, ""):
            return str(value)

    suffix = RedisKey(task.step_key).suffix
    if not suffix:
        raise ValueError(f"worker task step_key has no step suffix: {task.step_key!r}")

    return str(suffix)


def _default_failure_key(*, task: WorkerTask, step: Step) -> str:
    return RedisKey(
        kind="failure",
        identity=RedisKey(task.data_key).identity,
        suffix=_result_suffix(task=task, step=step),
    ).raw_key


__all__ = ["WorkerExecutor", "WorkerResult"]
