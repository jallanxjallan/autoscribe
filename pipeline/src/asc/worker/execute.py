"""Worker execution boundary.

The worker queue carries a Task key. The Task is only the custody/envelope
record. The executable runtime instruction is a Step key stored on the Task
as input_key/source_key.

Step records are Redis hash values. By the time the worker sees them, plan
step definitions have already been flattened into top-level string fields.
Do not parse args_json or reload/unpack the Plan here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from asc.models.process.result import Failure
from asc.models.process.step import Step
from asc.models.process.task import Task
from asc.redis.key import RedisKey
from asc.worker.engines import load_engine_call
from asc.worker.runtime_io import load_runtime_content


STEP_KEY_FIELDS = ("input_key", "source_key")


@dataclass(frozen=True, slots=True)
class WorkerResult:
    processed: int
    cursor_key: str | None
    task_key: str
    output_key: str


class WorkerExecutor:
    def execute(self, task_key: str) -> WorkerResult:
        task_key = _require_key(task_key, expected_kind="task", label="worker task")

        task: Task | None = None
        step: Step | None = None

        try:
            task = Task.load(task_key)

            step_key = _required_step_key(task, task_key)
            step = Step.load(step_key)

            input_content = load_runtime_content(step.call_key)

            args = _step_args(step)
            engine_call = load_engine_call(step.executor, args=args)
            outcome = engine_call(input_content)

            output_key = _output_key(task=task, step=step, outcome=outcome)
            outcome = _attach_worker_fields(
                outcome,
                task=task,
                step=step,
                task_key=task_key,
                step_key=step_key,
                output_key=output_key,
            )

        except Exception as exc:
            output_key, outcome = _failure_for_exception(
                task_key=task_key,
                task=task,
                step=step,
                exc=exc,
            )

        try:
            outcome.save(output_key)
        except AttributeError as exc:
            raise TypeError(
                f"Worker outcome {type(outcome).__name__} is not a "
                "RedisModel-compatible response/failure object"
            ) from exc

        return WorkerResult(
            processed=1,
            cursor_key=_optional_text(getattr(step, "cursor_key", None))
            or _optional_text(getattr(task, "cursor_key", None)) if task else None,
            task_key=task_key,
            output_key=output_key,
        )


def _required_step_key(task: Task, task_key: str) -> str:
    for name in STEP_KEY_FIELDS:
        value = _optional_text(getattr(task, name, None))
        if value:
            return _require_key(value, expected_kind="step", label=f"task {name}")

    choices = ", ".join(STEP_KEY_FIELDS)
    raise ValueError(f"worker task missing required step key field ({choices}): {task_key}")


def _require_key(value: object, *, expected_kind: str, label: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"{label} key is empty")

    if text.count(":") != 1:
        raise ValueError(f"{label} key must be a two-segment Redis key: {text!r}")

    key = RedisKey(text)
    if key.kind != expected_kind:
        raise ValueError(
            f"{label} key must have kind {expected_kind!r}, got {key.kind!r}: {text!r}"
        )

    return str(key)


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _step_args(step: Step) -> dict[str, Any]:
    """Build engine args from already-flattened Step fields.

    Redis hash values are strings by this point. Do not parse args_json.
    Do not derive missing fields from plan/cursor/index state.
    """

    excluded = {
        "identity",
        "call_key",
        "cursor_key",
        "step_number",
        "executor",
        "created_at",
    }

    payload: dict[str, Any] = {}

    for name, value in step.model_dump(mode="python").items():
        if name in excluded:
            continue

        text = _optional_text(value)
        if text is not None:
            payload[name] = text

    return payload


def _output_key(*, task: Task, step: Step, outcome: object) -> str:
    explicit = _optional_text(getattr(task, "output_key", None))
    if explicit:
        return explicit

    explicit = _optional_text(getattr(step, "output_key", None))
    if explicit:
        return explicit

    kind = _result_kind(outcome)

    # Step result keys should belong to the call/process identity, not the
    # worker task identity or the short-lived step identity.
    call_identity = RedisKey(step.call_key).identity
    return str(RedisKey(kind=kind, identity=call_identity))


def _failure_key(*, task_key: str, task: Task | None, step: Step | None) -> str:
    explicit = _optional_text(getattr(task, "failure_key", None)) if task else None
    if explicit:
        return explicit

    explicit = _optional_text(getattr(task, "output_key", None)) if task else None
    if explicit and explicit.startswith("failure:"):
        return explicit

    explicit = _optional_text(getattr(step, "failure_key", None)) if step else None
    if explicit:
        return explicit

    explicit = _optional_text(getattr(step, "output_key", None)) if step else None
    if explicit and explicit.startswith("failure:"):
        return explicit

    if step is not None:
        return str(RedisKey(kind="failure", identity=RedisKey(step.call_key).identity))

    if task is not None:
        return str(RedisKey(kind="failure", identity=task.identity))

    return str(RedisKey(kind="failure", identity=RedisKey(task_key).identity))


def _result_kind(outcome: object) -> str:
    name = type(outcome).__name__.lower()
    if "failure" in name or "error" in name:
        return "failure"
    return "response"


def _failure_for_exception(
    *,
    task_key: str,
    task: Task | None,
    step: Step | None,
    exc: Exception,
) -> tuple[str, Failure]:
    output_key = _failure_key(task_key=task_key, task=task, step=step)
    identity = RedisKey(output_key).identity

    failure = Failure(
        identity=identity,
        content="",
        failure_reason=type(exc).__name__,
        raw_json={
            "task_key": task_key,
            "step_key": _optional_text(getattr(step, "redis_key", None)) if step else None,
            "error": str(exc),
            "error_type": type(exc).__name__,
            "worker_boundary": "execute",
        },
    )

    return output_key, _attach_worker_fields(
        failure,
        task=task,
        step=step,
        task_key=task_key,
        step_key=_optional_text(getattr(step, "redis_key", None)),
        output_key=output_key,
    )


def _attach_worker_fields(
    outcome: object,
    *,
    task: Task | None,
    step: Step | None,
    task_key: str,
    step_key: str | None,
    output_key: str,
) -> object:
    """Copy worker/custody fields onto the saved response/failure."""

    identity = RedisKey(output_key).identity
    updates = {
        "identity": identity,
        "task_key": task_key,
        "task_identity": getattr(task, "identity", identity) if task else identity,
    }

    if step_key:
        updates["step_key"] = step_key
        updates["input_key"] = step_key
        updates["source_key"] = step_key

    if step is not None:
        updates["call_key"] = step.call_key
        updates["cursor_key"] = step.cursor_key
        updates["step_number"] = step.step_number
        updates["executor"] = step.executor
        updates["action"] = step.action

    elif task is not None:
        for name in ("cursor_key", "task_number", "step_number", "action", "executor"):
            value = getattr(task, name, None)
            if value is not None:
                updates[name] = value

    model_copy = getattr(outcome, "model_copy", None)
    if callable(model_copy):
        try:
            return model_copy(update=updates)
        except TypeError:
            pass

    for name, value in updates.items():
        try:
            setattr(outcome, name, value)
        except Exception:
            pass

    return outcome


__all__ = ["WorkerExecutor", "WorkerResult"]