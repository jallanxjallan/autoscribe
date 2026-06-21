from __future__ import annotations

"""Shared writer plumbing.

DEBT: the key-kind -> model mapping below is deliberately local for this
checkpoint. Move it to asc.registries next week when the model/action/table
contracts are consolidated.
"""


import importlib
from collections.abc import Mapping
from typing import Any

from asc.redis.key import RedisKey
from asc.scrivener.connect import LedgerConnection
from asc.scrivener.util import execute_and_commit


MODEL_PATH_BY_KEY_KIND = {
    "call": "asc.models.process.call.Call",
    "result": "asc.models.process.result.Result",
    "failure": "asc.models.process.result.Failure",
}


def redis_key(value: str, *, field: str = "source_key") -> RedisKey:
    return RedisKey(require_text(value, field))


def require_text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"scrivener task field must be a string: {field}")
    text = value.strip()
    if not text:
        raise ValueError(f"scrivener task missing required field: {field}")
    return text


def model_class_for_key(key: str) -> type[Any]:
    source = redis_key(key)
    try:
        dotted = MODEL_PATH_BY_KEY_KIND[source.kind]
    except KeyError as exc:
        expected = ", ".join(sorted(MODEL_PATH_BY_KEY_KIND))
        raise ValueError(
            f"no scrivener source loader for key kind {source.kind!r}; expected one of: {expected}"
        ) from exc

    module_name, class_name = dotted.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def load_source_key(key: str) -> Any:
    """Load the model object named by a ScrivenerTask.source_key."""

    source_key = require_text(key, "source_key")
    model_class = model_class_for_key(source_key)
    load = getattr(model_class, "load", None)
    if not callable(load):
        raise TypeError(f"{model_class.__name__} has no load() classmethod")
    return load(source_key)


def model_json(record: Any) -> str:
    return record.model_dump_json()


def insert_row(conn: LedgerConnection, table: str, row: Mapping[str, Any]) -> None:
    names = list(row)
    placeholders = ", ".join("?" for _ in names)
    quoted = ", ".join(f'"{name}"' for name in names)
    sql = f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})'
    execute_and_commit(conn, sql, tuple(row[name] for name in names))


__all__ = [
    "MODEL_PATH_BY_KEY_KIND",
    "insert_row",
    "ledger_identity",
    "load_source_key",
    "load_task_input",
    "load_task_output",
    "load_task_source",
    "model_class_for_key",
    "model_json",
    "redis_key",
    "require_text",
    "source_identity",
    "source_key",
    "step_number",
    "task_action",
    "task_number",
]

# Compatibility shims for callers outside asc.scrivener.writers.
# DEBT: delete this block after asc.scrivener.write stops importing task_action
# and any remaining call sites read task attributes directly or use RedisKey.
def task_action(task: Any) -> str:
    return require_text(task.action, "action")


def source_key(task: Any) -> str:
    return require_text(task.source_key, "source_key")


def source_identity(task: Any) -> str:
    return redis_key(task.source_key).identity


def ledger_identity(task: Any) -> str:
    return source_identity(task)


def task_number(task: Any) -> int:
    number = int(task.task_number)
    if number < 0:
        raise ValueError("task_number must be >= 0")
    return number


def step_number(task: Any) -> int:
    return task_number(task)


def load_task_input(task: Any) -> Any:
    return load_source_key(task.source_key)


def load_task_output(task: Any) -> Any:
    return load_source_key(task.source_key)


def load_task_source(task: Any) -> Any:
    return load_source_key(task.source_key)
