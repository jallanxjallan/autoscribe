from __future__ import annotations

import importlib
import json
from collections.abc import Mapping
from typing import Any

from asc.redis.key import RedisKey
from asc.scrivener.connect import LedgerConnection
from asc.scrivener.util import execute_and_commit


MODEL_PATH_BY_KIND = {
    "call": "asc.models.process.call.Call",
    "result": "asc.models.process.result.StepResult",
    "failure": "asc.models.process.failure.StepFailure",
}


def require_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"scrivener task field must be a string: {name}")
    value = value.strip()
    if not value:
        raise ValueError(f"scrivener task missing required field: {name}")
    return value


def redis_key(key: str) -> RedisKey:
    return RedisKey(require_text(key, "Redis key"))


def task_source_key(task: Any) -> str:
    return require_text(task.source_key, "source_key")


def source_key(task: Any) -> str:
    return task_source_key(task)


def source_kind(task: Any) -> str:
    return redis_key(task_source_key(task)).kind


def source_identity(task: Any) -> str:
    return redis_key(task_source_key(task)).identity


def ledger_identity(task: Any) -> str:
    return source_identity(task)


def cursor_key(task: Any) -> str:
    return require_text(task.cursor_key, "cursor_key")


def ledger_table(task: Any) -> str:
    return require_text(task.ledger_table, "ledger_table")


def action(task: Any) -> str:
    return require_text(task.action, "action")


def task_action(task: Any) -> str:
    return action(task)


def task_number(task: Any) -> int:
    number = int(task.task_number)
    if number < 0:
        raise ValueError("task_number must be >= 0")
    return number


def step_number(task: Any) -> int:
    return task_number(task)


def _model_class_for_key(key: str) -> type[Any]:
    kind = redis_key(key).kind
    try:
        dotted = MODEL_PATH_BY_KIND[kind]
    except KeyError as exc:
        expected = ", ".join(sorted(MODEL_PATH_BY_KIND))
        raise ValueError(f"no scrivener source loader for key kind {kind!r}; expected one of: {expected}") from exc

    module_name, class_name = dotted.rsplit(".", 1)
    module = importlib.import_module(module_name)
    model_class = getattr(module, class_name)
    return model_class


def load_source_key(key: str) -> Any:
    """Load the Redis object named by a task source key.

    Scrivener receives a ScrivenerTask. The task points at the real object to
    write through source_key: call:...:record, result:...:step.N, or
    failure:...:step.N. Keep Redis access behind the model .load() contract.
    """

    source = require_text(key, "source_key")
    model_class = _model_class_for_key(source)
    load = getattr(model_class, "load", None)
    if not callable(load):
        raise TypeError(f"{model_class.__name__} has no load() classmethod")
    return load(source)


def load_task_source(task: Any) -> Any:
    return load_source_key(task_source_key(task))


def load_task_input(task: Any) -> Any:
    return load_task_source(task)


def load_task_output(task: Any) -> Any:
    return load_task_source(task)


def model_dict(record: Any) -> dict[str, Any]:
    dump = record.model_dump
    return dict(dump(mode="json", exclude_none=True))


def json_text(value: object) -> str:
    if isinstance(value, str):
        json.loads(value)
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def model_json(record: Any) -> str:
    return record.model_dump_json()


def insert_row(conn: LedgerConnection, table: str, row: Mapping[str, Any]) -> None:
    names = list(row)
    placeholders = ", ".join("?" for _ in names)
    quoted = ", ".join(f'"{name}"' for name in names)
    sql = f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})'
    execute_and_commit(conn, sql, tuple(row[name] for name in names))


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
    "require_text",
    "source_identity",
    "source_key",
    "source_kind",
    "redis_key",
    "step_number",
    "task_action",
    "task_number",
    "task_source_key",
]
