"""Scrivener execution boundary."""

from __future__ import annotations

from dataclasses import dataclass

from asc.ledger.write import table_for_action, write_task
from asc.models.process.task import ScrivenerTask


@dataclass(frozen=True, slots=True)
class ScrivenerExecutionReport:
    """Report for one successful scrivener task execution.

    Scrivener is fire-and-forget from the orchestrator's perspective. A ledger
    write failure is not converted into a runtime artifact; it raises at the
    daemon boundary so the process supervisor can yell loudly.
    """

    task_key: str
    action: str
    table: str
    data_key: str


class ScrivenerExecutor:
    def execute(self, task_key: str) -> ScrivenerExecutionReport:
        task_key = _required_text(task_key, "scrivener task key")
        task = ScrivenerTask.load(task_key)
        _validate_task(task)
        write_task(task)

        return ScrivenerExecutionReport(
            task_key=task_key,
            action=task.action,
            table=table_for_action(task.action),
            data_key=task.data_key,
        )


def _validate_task(task: ScrivenerTask) -> None:
    if task.package != "scrivener":
        raise ValueError(f"scrivener executor received non-scrivener task: {task.raw_key}")

    if task.expected_key != task.data_key:
        raise ValueError(
            "scrivener task expected_key must match data_key: "
            f"expected_key={task.expected_key!r} data_key={task.data_key!r}"
        )


def _required_text(value: object, field: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"{field} must be non-empty")
    return text


__all__ = ["ScrivenerExecutionReport", "ScrivenerExecutor"]
