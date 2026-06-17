from __future__ import annotations

import importlib
import json
from collections.abc import Mapping
from typing import Any

from asc.scrivener.connect import LedgerConnection
from asc.scrivener.schema import table_columns
from asc.scrivener.util import execute_and_commit


_RUNTIME_MODEL_CANDIDATES: dict[str, tuple[tuple[str, str], ...]] = {
    "call": (
        ("asc.models.runtime.call", "CallRecord"),
        ("asc.models.process.call", "CallRecord"),
        ("asc.models.call", "CallRecord"),
    ),
    "result": (
        ("asc.models.runtime.result", "StepResult"),
        ("asc.models.process.result", "StepResult"),
        ("asc.models.runtime.step", "StepResult"),
    ),
    "failure": (
        ("asc.models.runtime.result", "StepFailure"),
        ("asc.models.process.result", "StepFailure"),
        ("asc.models.runtime.step", "StepFailure"),
    ),
}


def text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"scrivener task field must be a string: {name}")
    value = value.strip()
    if not value:
        raise ValueError(f"scrivener task missing required field: {name}")
    return value


def optional_text(value: object, default: str = "") -> str:
    if value in (None, ""):
        return default
    return str(value).strip()


def task_source_key(task: Any) -> str:
    return text(getattr(task, "source_key", None), "source_key")


def source_key(task: Any) -> str:
    return task_source_key(task)


def ledger_table(task: Any) -> str:
    return text(getattr(task, "ledger_table", None), "ledger_table")


def source_identity(task: Any) -> str:
    key = task_source_key(task)
    parts = key.split(":", 2)
    if len(parts) != 3 or not parts[1].strip():
        raise ValueError(f"cannot derive source identity from source_key: {key!r}")
    return parts[1].strip()


def ledger_identity(task: Any) -> str:
    return source_identity(task)


def cursor_key(task: Any) -> str:
    return text(getattr(task, "cursor_key", None), "cursor_key")


def task_number(task: Any) -> int:
    value = getattr(task, "task_number", None)
    if value in (None, ""):
        return 0
    number = int(value)
    if number < 0:
        raise ValueError("task_number must be >= 0")
    return number


def step_number(task: Any) -> int:
    return task_number(task)


def action(task: Any) -> str:
    return text(getattr(task, "action", None), "action")


def _source_kind(key: str) -> str:
    kind = key.split(":", 1)[0].strip()
    if not kind:
        raise ValueError(f"cannot derive model kind from source key: {key!r}")
    return kind


def load_source_key(key: str) -> Any:
    suffix = _source_kind(key)
    for module_name, class_name in _RUNTIME_MODEL_CANDIDATES.get(suffix, ()):
        try:
            module = importlib.import_module(module_name)
            model = getattr(module, class_name)
        except (ImportError, AttributeError):
            continue

        load = getattr(model, "load", None)
        if callable(load):
            return load(key)

    raise ValueError(f"no runtime model loader found for source key: {key}")


def load_task_source(task: Any) -> Any:
    return load_source_key(task_source_key(task))


def load_task_input(task: Any) -> Any:
    return load_task_source(task)


def load_task_output(task: Any) -> Any:
    return load_task_source(task)


def model_dict(record: Any) -> dict[str, Any]:
    if record is None:
        return {}

    dump = getattr(record, "model_dump", None)
    if callable(dump):
        return dict(dump(mode="json", exclude_none=True))

    if isinstance(record, Mapping):
        return {str(k): v for k, v in record.items() if v is not None}

    if hasattr(record, "__attrs_attrs__"):
        return {
            field.name: getattr(record, field.name)
            for field in record.__attrs_attrs__
            if getattr(record, field.name) is not None
        }

    return {
        key: value
        for key, value in vars(record).items()
        if not key.startswith("_") and value is not None
    }


def json_text(value: object) -> str:
    if value in (None, ""):
        return "{}"
    if isinstance(value, str):
        json.loads(value or "{}")
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def model_json(record: Any) -> str:
    return json.dumps(
        model_dict(record),
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def insert_row(conn: LedgerConnection, table: str, row: Mapping[str, Any]) -> None:
    columns = table_columns(conn, table)
    if not columns:
        raise RuntimeError(f"ledger table does not exist or has no columns: {table}")

    filtered = {key: value for key, value in row.items() if key in columns}

    if not filtered:
        raise ValueError(f"no insertable columns for ledger table: {table}")

    names = list(filtered)
    placeholders = ", ".join("?" for _ in names)
    quoted = ", ".join(f'"{name}"' for name in names)

    sql = f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})'
    execute_and_commit(conn, sql, tuple(filtered[name] for name in names))

def task_action(task: Any) -> str:
    return action(task)


__all__ = [
    "action",
    "cursor_key",
    "insert_row",
    "json_text",
    "ledger_identity",
    "ledger_table",
    "load_source_key",
    "load_task_input",
    "load_task_output",
    "load_task_source",
    "model_dict",
    "model_json",
    "optional_text",
    "source_identity",
    "source_key",
    "step_number",
    "task_number",
    "task_source_key",
    "task_action",
    "text",
    
]