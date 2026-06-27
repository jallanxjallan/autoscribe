"""Scrivener execution boundary."""

from __future__ import annotations

from dataclasses import dataclass

from asc.ledger.connect import connect
from asc.ledger.schema import ensure_ledger_schema
from asc.ledger.write import table_for, write_task, write_task_with_connection
from asc.models.process.result import Failure
from asc.models.process.task import Outcome, ScrivenerTask


SUCCESS = "success"


@dataclass(frozen=True, slots=True)
class _ExecutionReport:
    task_key: str
    outcome_key: str
    action: str


class ScrivenerExecutor:
    def execute(self, task_key: str) -> _ExecutionReport:
        task_key = _required_text(task_key, "scrivener task key")
        task = ScrivenerTask.load(task_key)

        try:
            with connect() as conn:
                ensure_ledger_schema(conn)
                write_task_with_connection(conn=conn, task=task)
        except Exception as exc:
            outcome_key = _save_failure_outcome(
                task=task,
                task_key=task_key,
                exc=exc,
            )
        else:
            outcome = Outcome.success(task=task, message=SUCCESS)
            outcome_key = outcome.save()

        return _ExecutionReport(
            task_key=task_key,
            outcome_key=outcome_key,
            action=task.action,
        )


def _save_failure_outcome(
    *,
    task: ScrivenerTask,
    task_key: str,
    exc: Exception,
) -> str:
    failure = _scrivener_failure(
        task=task,
        task_key=task_key,
        exc=exc,
    )
    failure_key = failure.save(identity=task.identity)
    outcome = Outcome.failure(task=task, message=failure_key)
    return outcome.save()


def _scrivener_failure(
    *,
    task: ScrivenerTask,
    task_key: str,
    exc: Exception,
) -> Failure:
    error = str(exc)
    try:
        table = table_for(task)
    except Exception:
        table = ""

    raw_json = {
        "task_key": task_key,
        "task_identity": task.identity,
        "data_key": task.data_key,
        "table": table,
        "action": task.action,
        "error": error,
        "error_type": type(exc).__name__,
        "boundary": "scrivener.ledger",
    }

    return Failure.model_validate(
        {
            "identity": task.identity,
            "failure_type": "scrivener",
            "content": error,
            "failure_reason": type(exc).__name__,
            "raw_json": raw_json,
            "boundary": "scrivener.ledger",
        }
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_text(value: object, field: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise ValueError(f"{field} must be non-empty")
    return text


__all__ = [
    "ScrivenerExecutor",
    "write_task",
    "write_task_with_connection",
]
