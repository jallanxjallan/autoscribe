"""Scrivener execution boundary.

The scrivener daemon owns claiming one task key and posting the saved outcome
key back to the orchestrator. This module owns loading the task, running the
ledger writer, and converting boundary failures into Outcome records.
"""

from dataclasses import dataclass
from typing import Any

from asc.models.process.task import Outcome, Task
from asc.redis.key import RedisKey


@dataclass(frozen=True, slots=True)
class ScrivenerResult:
    processed: int
    task_key: str
    output_key: str
    action: str | None = None


@dataclass(frozen=True, slots=True)
class Committed:
    """Local scrivener completion notice.

    A committed key is just the completed task copied under committed:<identity>.
    Its existence is the success signal.
    """

    task: Task
    task_key: str

    @property
    def identity(self) -> str:
        return self.task.identity

    @property
    def redis_key(self) -> RedisKey:
        return RedisKey(kind="committed", identity=self.identity)

    def save(self) -> str:
        committed = self.task.model_copy(
            update={
                "identity": self.identity,
                "task_identity": self.task.identity,
                "task_key": self.task_key,
            }
        )
        return committed.save(str(self.redis_key))


class ScrivenerExecutor:
    def execute(self, task_key: str) -> ScrivenerResult:
        task_key = _required_text(task_key, "scrivener task key")

        task: Task | None = None
        try:
            task = Task.load(task_key)

            # Smoke-test mode:
            # Re-enable this once scrivener writers understand the current
            # task/cursor/step contract.
            # write_task(task)

            outcome = _committed(task=task, task_key=task_key)

        except Exception as exc:
            outcome = _failure_outcome(task_key=task_key, task=task, exc=exc)

        output_key = outcome.save()
        return ScrivenerResult(
            processed=1,
            task_key=task_key,
            output_key=output_key,
            action=_optional_text(getattr(task, "action", None)) if task else None,
        )


def _committed(*, task: Task, task_key: str) -> Committed:
    return Committed(task=task, task_key=task_key)


def _failure_outcome(*, task_key: str, task: Task | None, exc: Exception) -> Outcome:
    payload: dict[str, Any]
    identity: str

    if task is not None:
        payload = task.model_dump(mode="json")
        identity = task.identity
    else:
        payload = {
            "task_key": task_key,
        }
        identity = RedisKey(task_key).identity

    package = _optional_text(getattr(task, "package", None)) if task else None
    action = _optional_text(getattr(task, "action", None)) if task else None

    return Outcome.model_validate(
        {
            **payload,
            "identity": identity,
            "task_identity": identity,
            "task_key": task_key,
            "package": package or "scrivener",
            "action": action or "",
            "result": "failure",
            "error": str(exc),
            "error_type": type(exc).__name__,
            "scrivener_boundary": "execute",
        }
    )


def _required_text(value: object, field: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"{field} must be non-empty")
    return text


def _optional_text(value: object) -> str | None:
    text = "" if value is not None else ""
    text = str(text).strip()
    return text or None


__all__ = ["ScrivenerExecutor", "ScrivenerResult"]