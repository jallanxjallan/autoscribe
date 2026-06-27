"""Shared Scrivener writer plumbing.

Scrivener receives task.source_key from the task model because that is the
cross-package contract. Inside this package, the key names a runtime record:
call, result, or failure. Keep domain names local and explicit so ledger fields
are not confused with Redis task attributes.

DEBT: the key-kind -> model mapping belongs in asc.registries when the runtime
model/action/table contracts are consolidated.
"""

import importlib
from collections.abc import Mapping
from typing import Any

from asc.redis.key import RedisKey
from asc.ledger.connect import LedgerConnection
from asc.ledger.util import execute_and_commit


MODEL_PATH_BY_KEY_KIND = {
    "call": "asc.models.process.call.CallRecord",
    "result": "asc.models.process.result.Result",
    "failure": "asc.models.process.result.Failure",
}


def require_text(value: object, field: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"scrivener missing required field: {field}")
    return text


def runtime_key(value: object, *, field: str) -> RedisKey:
    return RedisKey(require_text(value, field))


def task_action(task: Any) -> str:
    return require_text(task.action, "action")


def task_record_key(task: Any) -> RedisKey:
    return runtime_key(task.source_key, field="source_key")


def task_record_key_text(task: Any) -> str:
    return str(task_record_key(task))


def call_identity_from_key(key: RedisKey) -> str:
    return require_text(key.identity, "key.identity")


def task_call_identity(task: Any) -> str:
    return call_identity_from_key(task_record_key(task))


def optional_domain_identity(obj: object, *names: str) -> str | None:
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return require_text(value, name)
    return None


def model_class_for_key(key: object) -> type[Any]:
    runtime = runtime_key(key, field="source_key")
    try:
        dotted = MODEL_PATH_BY_KEY_KIND[runtime.kind]
    except KeyError as exc:
        expected = ", ".join(sorted(MODEL_PATH_BY_KEY_KIND))
        raise ValueError(
            f"no scrivener source loader for key kind {runtime.kind!r}; expected one of: {expected}"
        ) from exc

    module_name, class_name = dotted.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def load_record_key(key: object) -> Any:
    """Load the runtime model named by a ScrivenerTask.source_key."""

    key_text = require_text(key, "source_key")
    model_class = model_class_for_key(key_text)
    load = getattr(model_class, "load", None)
    if not callable(load):
        raise TypeError(f"{model_class.__name__} has no load() classmethod")
    return load(key_text)


def load_task_record(task: Any) -> Any:
    return load_record_key(task.source_key)


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
    "call_identity_from_key",
    "insert_row",
    "load_record_key",
    "load_task_record",
    "model_class_for_key",
    "model_json",
    "optional_domain_identity",
    "require_text",
    "runtime_key",
    "task_action",
    "task_call_identity",
    "task_record_key",
    "task_record_key_text",
]
