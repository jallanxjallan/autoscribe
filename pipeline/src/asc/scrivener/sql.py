"""Small guarded SQL primitives for Scrivener."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from asc.scrivener.connect import LedgerConnection
from asc.scrivener.maps import LEDGER_FIELDS
from asc.scrivener.util import execute_and_commit


class ScrivenerWriteError(RuntimeError):
    """Raised when SQLite rejects a Scrivener ledger write."""


def insert_row(
    conn: LedgerConnection,
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

    try:
        execute_and_commit(conn, sql, values)
    except sqlite3.Error as exc:
        message = (
            "sqlite rejected scrivener write: "
            f"table={table!r} data={dict(data)!r} "
            f"sqlite_error={str(exc)!r}"
        )
        raise ScrivenerWriteError(message) from exc


__all__ = ["ScrivenerWriteError", "insert_row"]
