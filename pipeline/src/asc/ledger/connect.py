from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Protocol

from asc.core.config import config as core_config


class LedgerCursor(Protocol):
    def fetchone(self) -> Any | None: ...

    def fetchall(self) -> list[Any]: ...


class LedgerConnection(Protocol):
    def execute(
        self,
        sql: str,
        parameters: Sequence[Any] | dict[str, Any] = (),
        /,
    ) -> LedgerCursor: ...

    def executemany(
        self,
        sql: str,
        seq_of_parameters: Iterable[Sequence[Any]],
        /,
    ) -> LedgerCursor: ...

    def commit(self) -> None: ...

    def close(self) -> None: ...


def configured_ledger_path() -> Path:
    """
    Return the configured SQLite ledger path.

    Config ownership stays in asc.core.config. This module is the only
    place that adapts that configured path into a SQLite connection.
    """

    return core_config.sql_ledger_path.expanduser()


def connect() -> sqlite3.Connection:
    ledger_path = configured_ledger_path()
    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(ledger_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


__all__ = [
    "LedgerConnection",
    "LedgerCursor",
    "configured_ledger_path",
    "connect",
]
