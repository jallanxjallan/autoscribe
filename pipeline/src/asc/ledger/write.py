"""Ledger write boundary for runtime custody tasks.

Scrivener owns daemon execution. Ledger owns action-to-table mapping, record
loading, row normalization, and SQLite writes.
"""

from __future__ import annotations

import importlib
from typing import Any

from asc.redis.key import RedisKey

from asc.ledger.connect import LedgerConnection, connect
from asc.ledger.maps import (
    ACTION_TABLES,
    CALLS_TABLE,
    CALL_COMPLETED_ACTION,
    CALL_FAILED_ACTION,
    CONFIRM_EXPORT_ACTION,
    EXPORTS_TABLE,
    FAILURE_RESULT_KIND,
    MODEL_PATH_BY_KEY_KIND,
    RESPONSES_TABLE,
    RESULT_KINDS,
    SUCCESS_RESULT_KINDS,
    WRITE_CALL_ACTION,
)
from asc.ledger.schema import ensure_ledger_schema
from asc.ledger.sql import insert_row
from asc.ledger.util import (
    model_json_blob,
    model_value,
    optional_text,
    required_text,
    result_timestamp,
    timestamp_now,
)


def write_task(task: object) -> None:
    with connect() as conn:
        ensure_ledger_schema(conn)
        write_task_with_connection(conn=conn, task=task)


def write_task_with_connection(*, conn: LedgerConnection, task: object) -> None:
    action = task_action(task)
    table = table_for_action(action)

    task_table = optional_text(getattr(task, "table", None))
    if task_table is not None and task_table != table:
        raise ValueError(
            f"scrivener task table mismatch for {action!r}: "
            f"task.table={task_table!r} ledger.table={table!r}"
        )

    if action == CONFIRM_EXPORT_ACTION:
        data = export_receipt_row(task=task)
        insert_row(conn, table=EXPORTS_TABLE, data=data)
        return

    record = load_record_key(task_data_key(task))
    data = row_for(action=action, task=task, record=record)
    insert_row(conn, table=table, data=data)


def table_for_action(action: str) -> str:
    try:
        return ACTION_TABLES[action]
    except KeyError as exc:
        expected = ", ".join(sorted(ACTION_TABLES))
        raise ValueError(
            f"unknown ledger task action: {action!r}; expected one of: {expected}"
        ) from exc


def row_for(*, action: str, task: object, record: object) -> dict[str, Any]:
    if action == WRITE_CALL_ACTION:
        return call_row(task=task, record=record)

    if action in {CALL_COMPLETED_ACTION, CALL_FAILED_ACTION}:
        return response_row(action=action, task=task, record=record)

    raise ValueError(f"unsupported ledger action for row construction: {action!r}")


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
        "source_json": model_json_blob(record),
        "created_at": int(model_value(record, "created_at")),
    }


def response_row(*, action: str, task: object, record: object) -> dict[str, Any]:
    data_key = task_data_key(task)
    key = RedisKey(data_key)
    if key.kind not in RESULT_KINDS:
        raise ValueError(f"terminal response task data_key must name a result/failure artifact: {data_key!r}")

    if action == CALL_FAILED_ACTION and key.kind != FAILURE_RESULT_KIND:
        raise ValueError(f"call_failed data_key must be a failure key: {data_key!r}")

    if action == CALL_COMPLETED_ACTION and key.kind not in SUCCESS_RESULT_KINDS:
        raise ValueError(f"call_completed data_key must be a success result key: {data_key!r}")

    status = response_status(action=action, record=record, result_kind=key.kind)

    return {
        # Primary key is the call identity, not the terminal Redis key.
        "identity": key.identity,
        "final_step": key_suffix_number(data_key, "task.data_key"),
        "result_key": data_key,
        "result_kind": key.kind,
        "status": status,
        "content": response_content(record=record, status=status),
        "fail_message": failure_message(record=record, status=status),
        "raw_json": model_json_blob(record),
        "created_at": int(result_timestamp(record)),
    }


def export_receipt_row(*, task: object) -> dict[str, Any]:
    now = int(timestamp_now())
    return {
        "response_identity": response_identity_from_task(task),
        "destination": optional_text(getattr(task, "destination", None)),
        "export_mode": optional_text(getattr(task, "export_mode", None)) or "manual",
        "target_slug": optional_text(getattr(task, "target_slug", None)),
        "target_path": optional_text(getattr(task, "target_path", None)),
        "exported_at": int(model_value(task, "exported_at", default=now)),
        "export_message": optional_text(
            model_value(task, "export_message", "message", default=None)
        ),
        "consumer_json": optional_text(model_value(task, "consumer_json", default=None)),
        "created_at": now,
    }


def response_identity_from_task(task: object) -> str:
    explicit = optional_text(
        model_value(task, "response_identity", "result_identity", "call_identity", default=None)
    )
    if explicit is not None:
        return identity_part(explicit)
    return RedisKey(task_data_key(task)).identity


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


def response_status(*, action: str, record: object, result_kind: str) -> str:
    if action == CALL_FAILED_ACTION or result_kind == FAILURE_RESULT_KIND:
        return "failure"

    value = optional_text(model_value(record, "status", default=None))
    if value is None:
        return "success"

    normalized = value.lower()
    if normalized in {"success", "completed", "complete", "ok"}:
        return "success"
    if normalized in {"failure", "failed", "error"}:
        return "failure"

    raise ValueError(f"unsupported response status: {value!r}")


def response_content(*, record: object, status: str) -> str | None:
    if status == "failure":
        return None
    return optional_text(model_value(record, "content", default=None))


def failure_message(*, record: object, status: str) -> str | None:
    if status != "failure":
        return None
    return optional_text(
        model_value(record, "fail_message", "failure_message", "content", default=None)
    )


def optional_domain_identity(obj: object, *names: str) -> str | None:
    for name in names:
        text = optional_text(model_value(obj, name, default=None))
        if text is not None:
            return text
    return None


def key_suffix_number(key: object, field: str) -> int:
    suffix = required_text(RedisKey(str(key)).suffix, f"{field}.suffix")
    number = int(suffix)
    if number < 1:
        raise ValueError(f"{field}.suffix must be >= 1: {number}")
    return number


def identity_part(value: str) -> str:
    text = required_text(value, "identity")
    parts = text.split(":")
    if len(parts) >= 2:
        return parts[1]
    return text


def task_action(task: object) -> str:
    return required_text(getattr(task, "action", None), "task.action")


def task_data_key(task: object) -> str:
    return required_text(getattr(task, "data_key", None), "task.data_key")


__all__ = [
    "call_row",
    "export_receipt_row",
    "failure_message",
    "identity_part",
    "key_suffix_number",
    "load_record_key",
    "optional_domain_identity",
    "response_content",
    "response_identity_from_task",
    "response_row",
    "response_status",
    "row_for",
    "table_for_action",
    "task_action",
    "task_data_key",
    "write_task",
    "write_task_with_connection",
]
