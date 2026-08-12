"""Direct Redis-artifact to SQLite ledger writes.

Scrivener supplies only an artifact key. The key kind selects the model and
ledger table. The persisted Redis hash must have exactly the same field names as
the destination row.
"""

from __future__ import annotations

import importlib
from typing import Any

from pydantic import BaseModel

from asc.ledger.connect import LedgerConnection, connect
from asc.ledger.maps import LEDGER_FIELDS, MODEL_PATH_BY_KEY_KIND, TABLE_BY_KEY_KIND
from asc.ledger.schema import ensure_ledger_schema, table_columns
from asc.ledger.sql import insert_row
from asc.redis.key import RedisKey


def table_for_key(key: str | RedisKey) -> str:
    redis_key = key if isinstance(key, RedisKey) else RedisKey(str(key))
    try:
        return TABLE_BY_KEY_KIND[redis_key.kind]
    except KeyError as exc:
        supported = ", ".join(sorted(TABLE_BY_KEY_KIND))
        raise ValueError(
            f"scrivener cannot persist key kind {redis_key.kind!r}; supported: {supported}"
        ) from exc


def write_key(key: str | RedisKey) -> str:
    redis_key = key if isinstance(key, RedisKey) else RedisKey(str(key))
    with connect() as conn:
        ensure_ledger_schema(conn)
        write_key_with_connection(conn=conn, key=redis_key)
    return redis_key.kind


def write_key_with_connection(*, conn: LedgerConnection, key: str | RedisKey) -> None:
    redis_key = key if isinstance(key, RedisKey) else RedisKey(str(key))
    table = table_for_key(redis_key)
    model_class = model_for_kind(redis_key.kind)
    require_model_table_parity(conn=conn, model_class=model_class, table=table)

    record = model_class.load(redis_key)
    row = record.model_dump(mode="json")

    expected = LEDGER_FIELDS[table]
    ordered = {field: row[field] for field in expected}
    if set(row) != set(expected):
        raise ValueError(
            f"Redis model/ledger row mismatch for {redis_key.raw_key}: "
            f"model={tuple(row)} ledger={expected}"
        )

    insert_row(conn, table=table, data=ordered)


def model_for_kind(kind: str) -> type[BaseModel]:
    try:
        dotted = MODEL_PATH_BY_KEY_KIND[kind]
    except KeyError as exc:
        raise ValueError(f"no ledger model registered for key kind {kind!r}") from exc

    module_name, class_name = dotted.rsplit(".", 1)
    model_class = getattr(importlib.import_module(module_name), class_name)
    if not isinstance(model_class, type) or not issubclass(model_class, BaseModel):
        raise TypeError(f"ledger model is not a Pydantic model: {dotted}")
    return model_class


def require_model_table_parity(
    *,
    conn: LedgerConnection,
    model_class: type[BaseModel],
    table: str,
) -> None:
    model_fields = tuple(model_class.model_fields)
    ledger_fields = LEDGER_FIELDS[table]
    actual_columns = table_columns(conn, table)

    if model_fields != ledger_fields:
        raise RuntimeError(
            f"model/table field order mismatch for {table}: "
            f"model={model_fields!r} ledger={ledger_fields!r}"
        )
    if actual_columns != set(ledger_fields):
        raise RuntimeError(
            f"SQLite table/model field mismatch for {table}: "
            f"table={tuple(sorted(actual_columns))!r} model={model_fields!r}"
        )

    missing_required = tuple(
        name for name, field in model_class.model_fields.items() if field.is_required() and name not in actual_columns
    )
    if missing_required:
        raise RuntimeError(
            f"SQLite table {table!r} is missing mandatory model fields: {missing_required!r}"
        )


__all__ = [
    "model_for_kind",
    "require_model_table_parity",
    "table_for_key",
    "write_key",
    "write_key_with_connection",
]
