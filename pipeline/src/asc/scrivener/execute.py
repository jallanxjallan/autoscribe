"""Scrivener execution boundary."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from asc.models.process.result import Failure
from asc.models.process.task import Outcome, ScrivenerTask
from asc.redis.key import RedisKey
from asc.scrivener.connect import connect
from asc.scrivener.maps import (
    ACTION_TABLES,
    CALLS_TABLE,
    CONFIRM_EXPORT_ACTION,
    EXPORTS_TABLE,
    LEDGER_FIELDS,
    MODEL_PATH_BY_KEY_KIND,
    STEPS_TABLE,
)
from asc.scrivener.queries import CONFIRM_EXPORT_SQL
from asc.scrivener.schema import ensure_ledger_schema
from asc.scrivener.sql import execute_update, insert_row
from asc.scrivener.util import timestamp_now


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


def write_task(task: ScrivenerTask) -> None:
    with connect() as conn:
        ensure_ledger_schema(conn)
        write_task_with_connection(conn=conn, task=task)


def write_task_with_connection(*, conn: object, task: ScrivenerTask) -> None:
    if task.action == CONFIRM_EXPORT_ACTION:
        execute_update(conn, CONFIRM_EXPORT_SQL, confirm_export_values(task))
        return

    record = load_record_key(task.data_key)
    table = table_for(task)
    data = row_for(task=task, record=record)
    insert_row(conn, table=table, data=data)


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


def table_for(task: ScrivenerTask) -> str:
    action = _required_text(task.action, "task.action")
    try:
        return ACTION_TABLES[action]
    except KeyError as exc:
        expected = ", ".join(sorted(ACTION_TABLES))
        raise ValueError(
            f"unknown scrivener task action: {action!r}; expected one of: {expected}"
        ) from exc


def row_for(*, task: ScrivenerTask, record: object) -> dict[str, Any]:
    table = table_for(task)
    if table not in LEDGER_FIELDS:
        raise ValueError(f"unknown scrivener ledger table: {table!r}")

    if table == CALLS_TABLE:
        return call_row(task=task, record=record)

    if table == STEPS_TABLE:
        return step_row(task=task, record=record)

    if table == EXPORTS_TABLE:
        return export_row(task=task, record=record)

    raise ValueError(f"unsupported scrivener ledger table: {table!r}")


def call_row(*, task: ScrivenerTask, record: object) -> dict[str, Any]:
    data_key = _required_text(task.data_key, "task.data_key")
    identity = RedisKey(data_key).identity
    source_identity = _optional_domain_identity(
        record,
        "source_identity",
        "record_identity",
        "document_identity",
    ) or identity

    return {
        "identity": identity,
        "source_identity": source_identity,
        "source_json": _model_json(record),
        "created_at": int(getattr(record, "created_at")),
    }


def step_row(*, task: ScrivenerTask, record: object) -> dict[str, Any]:
    data_key = _required_text(task.data_key, "task.data_key")
    return {
        "identity": RedisKey(data_key).identity,
        "step_number": _key_suffix_number(data_key, "task.data_key"),
        "result_key": data_key,
        "status": _step_status(record),
        "content": _optional_text(getattr(record, "content", None)),
        "fail_message": _failure_message(record),
        "raw_json": _model_json(record),
        "created_at": int(getattr(record, "created_at")),
    }


def export_row(*, task: ScrivenerTask, record: object) -> dict[str, Any]:
    data_key = _required_text(task.data_key, "task.data_key")
    identity = RedisKey(data_key).identity
    source_identity = _optional_domain_identity(
        record,
        "source_identity",
        "record_identity",
        "document_identity",
    ) or identity

    return {
        "identity": identity,
        "source_identity": source_identity,
        "final_step": _key_suffix_number(data_key, "task.data_key"),
        "result_key": data_key,
        "exported_at": None,
        "export_message": None,
        "created_at": int(getattr(record, "created_at")),
    }


def confirm_export_values(task: ScrivenerTask) -> tuple[Any, ...]:
    return (
        int(timestamp_now()),
        _optional_text(getattr(task, "message", None)),
        RedisKey(task.data_key).identity,
    )


def load_record_key(key: object) -> Any:
    key_text = _required_text(key, "data_key")
    runtime = RedisKey(key_text)
    try:
        dotted = MODEL_PATH_BY_KEY_KIND[runtime.kind]
    except KeyError as exc:
        expected = ", ".join(sorted(MODEL_PATH_BY_KEY_KIND))
        raise ValueError(
            f"no scrivener loader for key kind {runtime.kind!r}; expected one of: {expected}"
        ) from exc

    module_name, class_name = dotted.rsplit(".", 1)
    module = importlib.import_module(module_name)
    model_class = getattr(module, class_name)
    load = getattr(model_class, "load", None)
    if not callable(load):
        raise TypeError(f"{model_class.__name__} has no load() classmethod")
    return load(key_text)


def _step_status(record: object) -> str:
    return "failed" if isinstance(record, Failure) else "completed"


def _failure_message(record: object) -> str | None:
    if not isinstance(record, Failure):
        return None
    return _optional_text(getattr(record, "content", None))


def _model_json(record: object) -> str:
    dump = getattr(record, "model_dump_json", None)
    if not callable(dump):
        raise TypeError(f"{type(record).__name__} has no model_dump_json()")
    return dump()


def _optional_domain_identity(obj: object, *names: str) -> str | None:
    for name in names:
        value = getattr(obj, name, None)
        text = _optional_text(value)
        if text is not None:
            return text
    return None


def _key_suffix_number(key: object, field: str) -> int:
    suffix = _required_text(RedisKey(str(key)).suffix, f"{field}.suffix")
    number = int(suffix)
    if number < 1:
        raise ValueError(f"{field}.suffix must be >= 1: {number}")
    return number


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
    "call_row",
    "confirm_export_values",
    "export_row",
    "load_record_key",
    "row_for",
    "step_row",
    "table_for",
    "write_task",
    "write_task_with_connection",
]
