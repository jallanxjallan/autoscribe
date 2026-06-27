"""Small guarded SQL primitives for Scrivener."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from asc.ledger.maps import LEDGER_FIELDS
from asc.ledger.util import execute_and_commit


class ScrivenerWriteError(RuntimeError):
    """Raised when SQLite rejects a Scrivener ledger write."""


def insert_row(
    conn: object,
    *,
    table: str,
    data: Mapping[str, Any],
) -> None:
    """Insert an exact-shape data hash into a known ledger table."""

    expected = LEDGER_FIELDS.get(table)
    if expected is None:
        raise ValueError(f"unknown scrivener ledger table: {table!r}")

    actual = tuple(data.keys())
    if actual != expected:
        raise ValueError(
            f"scrivener row shape mismatch for {table!r}: "
            f"expected {expected!r}, got {actual!r}"
        )

    columns = ", ".join(f'"{name}"' for name in expected)
    placeholders = ", ".join("?" for _ in expected)
    sql = f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})'
    values = tuple(data[name] for name in expected)
    execute_update(conn, sql, values, table=table, data=data)


def execute_update(
    conn: object,
    sql: str,
    values: Sequence[Any],
    *,
    table: str | None = None,
    data: Mapping[str, Any] | None = None,
) -> None:
    try:
        execute_and_commit(conn, sql, tuple(values))
    except sqlite3.Error as exc:
        details = ""
        if table is not None:
            details += f" table={table!r}"
        if data is not None:
            details += f" data={dict(data)!r}"
        message = (
            "sqlite rejected scrivener write:"
            f"{details} sqlite_error={str(exc)!r}"
        )
        raise ScrivenerWriteError(message) from exc


__all__ = ["ScrivenerWriteError", "execute_update", "insert_row"]
