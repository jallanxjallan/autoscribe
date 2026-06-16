from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from asc.scrivener.connect import LedgerConnection, connect
from asc.scrivener.schema import ensure_ledger_schema


@dataclass(frozen=True)
class SchemaColumn:
    table: str
    cid: int
    name: str
    column_type: str
    not_null: bool
    default_value: str | None
    primary_key: int


@dataclass(frozen=True)
class SchemaDDL:
    name: str
    sql: str


def schema_columns() -> list[SchemaColumn]:
    """Return column metadata for all user ledger tables."""

    with connect() as conn:
        ensure_ledger_schema(conn)
        return schema_columns_with_connection(conn)


def schema_columns_with_connection(conn: LedgerConnection) -> list[SchemaColumn]:
    rows: list[SchemaColumn] = []
    for table in ledger_table_names_with_connection(conn):
        cursor = conn.execute(f"PRAGMA table_info({table})")
        for row in cursor.fetchall():
            rows.append(
                SchemaColumn(
                    table=table,
                    cid=int(row[0]),
                    name=str(row[1]),
                    column_type=str(row[2] or ""),
                    not_null=bool(row[3]),
                    default_value=None if row[4] is None else str(row[4]),
                    primary_key=int(row[5]),
                )
            )
    return rows


def schema_sql() -> list[SchemaDDL]:
    """Return raw CREATE statements for all user ledger tables."""

    with connect() as conn:
        ensure_ledger_schema(conn)
        return schema_sql_with_connection(conn)


def schema_sql_with_connection(conn: LedgerConnection) -> list[SchemaDDL]:
    cursor = conn.execute(
        """
        SELECT name, sql
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name ASC
        """
    )
    return [SchemaDDL(name=str(row[0]), sql=str(row[1] or "")) for row in cursor.fetchall()]


def ledger_table_names() -> list[str]:
    with connect() as conn:
        ensure_ledger_schema(conn)
        return ledger_table_names_with_connection(conn)


def ledger_table_names_with_connection(conn: LedgerConnection) -> list[str]:
    cursor = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name ASC
        """
    )
    return [str(row[0]) for row in cursor.fetchall()]


__all__ = [
    "SchemaColumn",
    "SchemaDDL",
    "ledger_table_names",
    "ledger_table_names_with_connection",
    "schema_columns",
    "schema_columns_with_connection",
    "schema_sql",
    "schema_sql_with_connection",
]
