import json
from collections.abc import Iterable, Sequence
from typing import Any

from asc.scrivener.connect import LedgerConnection


SqlParams = Sequence[Any] | dict[str, Any]


def insert_sql(table: str, columns: Sequence[str]) -> str:
    """Render an explicit INSERT statement for ledger custody writes.

    Ledger writes should fail loudly on duplicate/conflicting identities. Silent
    INSERT OR IGNORE behavior hides custody bugs.
    """

    cols = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    return f"""
    INSERT INTO {table}
    ({cols})
    VALUES ({placeholders})
    """


def json_blob(value: object) -> str:
    if isinstance(value, str):
        return value

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def model_value(obj: object, *names: str, default: Any = None) -> Any:
    """Read the first present attribute/key from a model-like object."""

    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


def model_json_blob(obj: object) -> str:
    """Serialize a Pydantic model, mapping, or plain object for forensics."""

    if hasattr(obj, "model_dump"):
        return json_blob(obj.model_dump(mode="json"))  # type: ignore[attr-defined]
    if isinstance(obj, dict):
        return json_blob(obj)
    return json_blob(vars(obj))


def row_dict(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def rows_dict(rows: Iterable[Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def fetch_one_dict(
    conn: LedgerConnection,
    sql: str,
    parameters: SqlParams = (),
) -> dict[str, Any] | None:
    return row_dict(conn.execute(sql, parameters).fetchone())


def fetch_all_dicts(
    conn: LedgerConnection,
    sql: str,
    parameters: SqlParams = (),
) -> list[dict[str, Any]]:
    return rows_dict(conn.execute(sql, parameters).fetchall())


def fetch_first_column(
    conn: LedgerConnection,
    sql: str,
    parameters: SqlParams = (),
) -> list[str]:
    rows = conn.execute(sql, parameters).fetchall()
    return [str(row[0]) for row in rows]


def execute_and_commit(
    conn: LedgerConnection,
    sql: str,
    values: Sequence[Any],
) -> None:
    conn.execute(sql, values)
    conn.commit()


def executemany_and_commit(
    conn: LedgerConnection,
    sql: str,
    values: Iterable[Sequence[Any]],
) -> None:
    conn.executemany(sql, values)
    conn.commit()


def result_timestamp(result: object) -> int:
    """Choose the best timestamp available on a runtime result-like object."""

    from asc.core.timestamp import timestamp

    if model_value(result, "completed_at") is not None:
        return int(model_value(result, "completed_at"))

    if model_value(result, "started_at") is not None:
        return int(model_value(result, "started_at"))

    if model_value(result, "created_at") is not None:
        return int(model_value(result, "created_at"))

    return timestamp()


def timestamp_now() -> int:
    from asc.core.timestamp import timestamp

    return int(timestamp())


__all__ = [
    "SqlParams",
    "execute_and_commit",
    "executemany_and_commit",
    "fetch_all_dicts",
    "fetch_first_column",
    "fetch_one_dict",
    "insert_sql",
    "json_blob",
    "model_json_blob",
    "model_value",
    "result_timestamp",
    "row_dict",
    "rows_dict",
    "timestamp_now",
]
