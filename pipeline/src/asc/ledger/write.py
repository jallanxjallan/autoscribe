"""Ledger write boundary for runtime task records.

Scrivener owns task execution. Ledger owns the SQLite persistence contract:
action-to-table mapping, row normalization, and inserts/updates.
"""

from __future__ import annotations

import importlib
from typing import Any

from asc.models.process.result import Failure
from asc.redis.key import RedisKey
from asc.ledger.connect import connect
from asc.ledger.maps import (
    ACTION_TABLES,
    CALLS_TABLE,
    CONFIRM_EXPORT_ACTION,
    EXPORTS_TABLE,
    LEDGER_FIELDS,
    MODEL_PATH_BY_KEY_KIND,
    STEPS_TABLE,
)
from asc.ledger.queries import CONFIRM_EXPORT_SQL
from asc.ledger.schema import ensure_ledger_schema
from asc.ledger.sql import execute_update, insert_row
from asc.ledger.util import timestamp_now


def write_task(task: object) -> None:
    with connect() as conn:
        ensure_ledger_schema(conn)
        write_task_with_connection(conn=conn, task=task)


def write_task_with_connection(*, conn: object, task: object) -> None:
    if task_action(task) == CONFIRM_EXPORT_ACTION:
        execute_update(conn, CONFIRM_EXPORT_SQL, confirm_export_values(task))
        return

    record = load_record_key(task_data_key(task))
    table = table_for(task)
    data = row_for(task=task, record=record)
    insert_row(conn, table=table, data=data)


def table_for(task: object) -> str:
    action = task_action(task)
    try:
        return ACTION_TABLES[action]
    except KeyError as exc:
        expected = ", ".join(sorted(ACTION_TABLES))
        raise ValueError(
            f"unknown ledger task action: {action!r}; expected one of: {expected}"
        ) from exc


def row_for(*, task: object, record: object) -> dict[str, Any]:
    table = table_for(task)
    if table not in LEDGER_FIELDS:
        raise ValueError(f"unknown ledger table: {table!r}")

    if table == CALLS_TABLE:
        return call_row(task=task, record=record)

    if table == STEPS_TABLE:
        return step_row(task=task, record=record)

    if table == EXPORTS_TABLE:
        return export_row(task=task, record=record)

    raise ValueError(f"unsupported ledger table: {table!r}")


def call_row(*, task: object, record: object) -> dict[str, Any]:
    data_key = task_data_key(task)
    identity = RedisKey(data_key).identity
    source_identity = optional_domain_identity(
        record,
        "source_identity",
        "record_identity",
        "document_identity",
    ) or identity

    return {
        "identity": identity,
        "source_identity": source_identity,
        "source_json": model_json(record),
        "created_at": int(getattr(record, "created_at")),
    }


def step_row(*, task: object, record: object) -> dict[str, Any]:
    data_key = task_data_key(task)
    return {
        "identity": RedisKey(data_key).identity,
        "step_number": key_suffix_number(data_key, "task.data_key"),
        "result_key": data_key,
        "status": step_status(record),
        "content": optional_text(getattr(record, "content", None)),
        "fail_message": failure_message(record),
        "raw_json": model_json(record),
        "created_at": int(getattr(record, "created_at")),
    }


def export_row(*, task: object, record: object) -> dict[str, Any]:
    data_key = task_data_key(task)
    identity = RedisKey(data_key).identity
    source_identity = optional_domain_identity(
        record,
        "source_identity",
        "record_identity",
        "document_identity",
    ) or identity

    return {
        "identity": identity,
        "source_identity": source_identity,
        "final_step": key_suffix_number(data_key, "task.data_key"),
        "result_key": data_key,
        "exported_at": None,
        "export_message": None,
        "created_at": int(getattr(record, "created_at")),
    }


def confirm_export_values(task: object) -> tuple[Any, ...]:
    return (
        int(timestamp_now()),
        optional_text(getattr(task, "message", None)),
        RedisKey(task_data_key(task)).identity,
    )


def load_record_key(key: object) -> Any:
    key_text = required_text(key, "data_key")
    runtime = RedisKey(key_text)
    try:
        dotted = MODEL_PATH_BY_KEY_KIND[runtime.kind]
    except KeyError as exc:
        expected = ", ".join(sorted(MODEL_PATH_BY_KEY_KIND))
        raise ValueError(
            f"no ledger loader for key kind {runtime.kind!r}; expected one of: {expected}"
        ) from exc

    module_name, class_name = dotted.rsplit(".", 1)
    module = importlib.import_module(module_name)
    model_class = getattr(module, class_name)
    load = getattr(model_class, "load", None)
    if not callable(load):
        raise TypeError(f"{model_class.__name__} has no load() classmethod")
    return load(key_text)


def step_status(record: object) -> str:
    return "failed" if isinstance(record, Failure) else "completed"


def failure_message(record: object) -> str | None:
    if not isinstance(record, Failure):
        return None
    return optional_text(getattr(record, "content", None))


def model_json(record: object) -> str:
    dump = getattr(record, "model_dump_json", None)
    if not callable(dump):
        raise TypeError(f"{type(record).__name__} has no model_dump_json()")
    return dump()


def optional_domain_identity(obj: object, *names: str) -> str | None:
    for name in names:
        text = optional_text(getattr(obj, name, None))
        if text is not None:
            return text
    return None


def key_suffix_number(key: object, field: str) -> int:
    suffix = required_text(RedisKey(str(key)).suffix, f"{field}.suffix")
    number = int(suffix)
    if number < 1:
        raise ValueError(f"{field}.suffix must be >= 1: {number}")
    return number


def task_action(task: object) -> str:
    return required_text(getattr(task, "action", None), "task.action")


def task_data_key(task: object) -> str:
    return required_text(getattr(task, "data_key", None), "task.data_key")


def optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def required_text(value: object, field: str) -> str:
    text = optional_text(value)
    if text is None:
        raise ValueError(f"{field} must be non-empty")
    return text


__all__ = [
    "call_row",
    "confirm_export_values",
    "export_row",
    "failure_message",
    "key_suffix_number",
    "load_record_key",
    "model_json",
    "optional_domain_identity",
    "optional_text",
    "required_text",
    "row_for",
    "step_row",
    "step_status",
    "table_for",
    "task_action",
    "task_data_key",
    "write_task",
    "write_task_with_connection",
]
