import sqlite3
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from asc.core.config import config


@runtime_checkable
class LedgerConnectionProtocol(Protocol):
    """Structural contract for objects usable as ledger connections.

    This stays as a typing/interface concept only.  Do not instantiate it.
    """

    row_factory: Any

    def execute(self, sql: str, parameters: object = ...) -> sqlite3.Cursor: ...
    def executemany(self, sql: str, seq_of_parameters: object) -> sqlite3.Cursor: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...

    def __enter__(self) -> "LedgerConnectionProtocol": ...
    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool | None: ...


class LedgerConnection:
    """Concrete ledger connection factory.

    This class exists so callers may write ``LedgerConnection()`` without
    confusing a typing Protocol with a runtime constructor.  It returns the
    configured SQLite ledger connection for now.  Future database-specific
    connection classes can follow the same pattern.
    """

    def __new__(cls) -> sqlite3.Connection:
        return connect()


class SQLiteLedgerConnection(LedgerConnection):
    """Explicit SQLite ledger connection factory alias."""


LedgerConnectionLike = LedgerConnectionProtocol


def configured_ledger_path() -> Path:
    """Return the configured filesystem path for the active ledger database."""

    return config.sql_ledger_path


def connect() -> sqlite3.Connection:
    """Open the active SQLite ledger connection."""

    path = configured_ledger_path().expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


__all__ = [
    "LedgerConnection",
    "LedgerConnectionLike",
    "LedgerConnectionProtocol",
    "SQLiteLedgerConnection",
    "configured_ledger_path",
    "connect",
]
