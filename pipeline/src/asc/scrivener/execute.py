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
    CALLS_TABLE,
    EXPORTS_TABLE,
    LEDGER_FIELDS,
    MODEL_PATH_BY_KEY_KIND,
    STEPS_TABLE,
    STEP_STATUS_BY_KEY_KIND,
)
from asc.scrivener.schema import ensure_ledger_schema
from asc.scrivener.sql import insert_row


@dataclass(frozen=True, slots=True)
class ScrivenerResult:
    processed: int
    task_key: str
    outcome_key: str
    action: str | None = None


class ScrivenerExecutor:
    def execute(self, task_key: str) -> ScrivenerResult:
        task_key = _required_text(task_key, "scrivener task key")

        task: ScrivenerTask | None = None
        try:
            task = ScrivenerTask.load(task_key)
            record = load_record_key(task.data_key)
            data = row_for(table=task.table, data_key=task.data_key, record=record)

            with connect() as conn:
                ensure_ledger_schema(conn)
                insert_row(conn, table=task.table, data=data)

            outcome = Outcome.success(task_key=task_key, task=task)

        except Exception as exc:
            failure = Failure.internal(
                task_key=task_key,
                task=task,
                exc=exc,
                boundary="scrivener.execute",
                data_key=getattr(task, "data_key", None),
                table=getattr(task, "table", None),
            )
            failure_key = failure.save()
            outcome = _failure_outcome(
                task_key=task_key,
                task=task,
                failure_key=failure_key,
                exc=exc,
            )

        outcome_key = outcome.save()
        return ScrivenerResult(
            processed=1,
            task_key=task_key,
            outcome_key=outcome_key,
            action=_optional_text(getattr(task, "action", None)) if task else None,
        )


def row_for(*, table: str, data_key: str, record: object) -> dict[str, Any]:
    if table not in LEDGER_FIELDS:
        raise ValueError(f"unknown scrivener ledger table: {table!r}")

    if table == CALLS_TABLE:
        return call_row(data_key=data_key, record=record)

    if table == STEPS_TABLE:
        return step_row(data_key=data_key, record=record)

    if table == EXPORTS_TABLE:
        return export_row(data_key=data_key, record=record)

    raise ValueError(f"unsupported scrivener ledger table: {table!r}")


def call_row(*, data_key: str, record: object) -> dict[str, Any]:
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


def step_row(*, data_key: str, record: object) -> dict[str, Any]:
    key = RedisKey(data_key)
    return {
        "identity": key.identity,
        "step_number": _positive_int(getattr(record, "step_number"), "step_number"),
        "result_key": str(data_key),
        "status": _step_status(data_key),
        "content": getattr(record, "content"),
        "fail_message": _failure_message(data_key=data_key, record=record),
        "raw_json": _model_json(record),
        "created_at": int(getattr(record, "created_at")),
    }


def export_row(*, data_key: str, record: object) -> dict[str, Any]:
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
        "final_step": _positive_int(getattr(record, "final_step"), "final_step"),
        "result_key": str(data_key),
        "exported_at": int(getattr(record, "exported_at")),
        "export_message": getattr(record, "export_message"),
        "created_at": int(getattr(record, "created_at")),
    }


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


def _failure_outcome(
    *,
    task_key: str,
    task: ScrivenerTask | None,
    failure_key: str,
    exc: Exception,
) -> Outcome:
    if task is not None:
        return Outcome.failure(
            task_key=task_key,
            task=task,
            failure_key=failure_key,
            error=str(exc),
            error_type=type(exc).__name__,
            boundary="scrivener.execute",
        )

    identity = RedisKey(task_key).identity
    return Outcome.model_validate(
        {
            "identity": identity,
            "task_identity": identity,
            "task_key": task_key,
            "package": "scrivener",
            "action": "execute",
            "status": "failure",
            "failure_key": failure_key,
            "error": str(exc),
            "error_type": type(exc).__name__,
            "boundary": "scrivener.execute",
        }
    )


def _step_status(data_key: str) -> str:
    kind = RedisKey(data_key).kind
    try:
        return STEP_STATUS_BY_KEY_KIND[kind]
    except KeyError as exc:
        expected = ", ".join(sorted(STEP_STATUS_BY_KEY_KIND))
        raise ValueError(f"unsupported step data key kind: {kind!r}; expected one of: {expected}") from exc


def _failure_message(*, data_key: str, record: object) -> str | None:
    if _step_status(data_key) != "failed":
        return None

    for name in ("content", "fail_message", "error", "message"):
        value = getattr(record, name, None)
        if value not in (None, ""):
            return str(value)
    return None


def _model_json(record: object) -> str:
    dump = getattr(record, "model_dump_json", None)
    if not callable(dump):
        raise TypeError(f"{type(record).__name__} has no model_dump_json()")
    return dump()


def _optional_domain_identity(obj: object, *names: str) -> str | None:
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return _required_text(value, name)
    return None


def _positive_int(value: object, field: str) -> int:
    number = int(value)
    if number < 1:
        raise ValueError(f"{field} must be >= 1: {number}")
    return number


def _required_text(value: object, field: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"{field} must be non-empty")
    return text


def _optional_text(value: object) -> str | None:
    text = "" if value is None else str(value).strip()
    return text or None


__all__ = [
    "ScrivenerExecutor",
    "ScrivenerResult",
    "call_row",
    "export_row",
    "load_record_key",
    "row_for",
    "step_row",
]
