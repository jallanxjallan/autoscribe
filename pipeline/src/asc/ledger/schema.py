from collections.abc import Iterable

from asc.ledger.connect import LedgerConnection
from asc.ledger.views import CREATE_LEDGER_VIEWS_SQL, LEDGER_VIEW_NAMES

ColumnSpec = dict[str, str | list[str]]


def create_table_sql(name: str, columns: ColumnSpec) -> str:
    column_defs: list[str] = []
    constraints: list[str] = []

    for column_name, spec in columns.items():
        if column_name == "__constraints__":
            constraints.extend(spec)  # type: ignore[arg-type]
        else:
            column_defs.append(f"{column_name} {spec}")

    rendered = ",\n    ".join(column_defs + constraints)
    return f"""
CREATE TABLE IF NOT EXISTS {name} (
    {rendered}
);
"""


def ensure_schema(
    conn: LedgerConnection,
    tables: dict[str, ColumnSpec],
    indexes: Iterable[str] = (),
    views: Iterable[str] = (),
) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    for table_name, columns in tables.items():
        conn.execute(create_table_sql(table_name, columns))
    for statement in indexes:
        conn.execute(statement)
    for statement in views:
        conn.execute(statement)
    conn.commit()


def _foreign_keys_enabled(conn: LedgerConnection) -> bool:
    row = conn.execute("PRAGMA foreign_keys").fetchone()
    return bool(row[0]) if row is not None else True


def _set_foreign_keys(conn: LedgerConnection, *, enabled: bool) -> None:
    conn.execute(f"PRAGMA foreign_keys = {'ON' if enabled else 'OFF'}")


def drop_views(conn: LedgerConnection, view_names: Iterable[str]) -> None:
    for view_name in view_names:
        conn.execute(f'DROP VIEW IF EXISTS "{view_name}"')
    conn.commit()


def drop_tables(conn: LedgerConnection, table_names: Iterable[str]) -> None:
    was_enabled = _foreign_keys_enabled(conn)
    try:
        if was_enabled:
            _set_foreign_keys(conn, enabled=False)
        for table_name in table_names:
            conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
    finally:
        if was_enabled:
            _set_foreign_keys(conn, enabled=True)
    conn.commit()


def drop_user_objects(conn: LedgerConnection) -> None:
    was_enabled = _foreign_keys_enabled(conn)
    try:
        if was_enabled:
            _set_foreign_keys(conn, enabled=False)
        rows = conn.execute(
            """
            SELECT type, name
            FROM sqlite_master
            WHERE type IN ('view', 'table', 'index')
              AND name NOT LIKE 'sqlite_%'
            ORDER BY
              CASE type
                WHEN 'view' THEN 0
                WHEN 'table' THEN 1
                ELSE 2
              END
            """
        ).fetchall()
        for obj_type, name in rows:
            if obj_type == "view":
                conn.execute(f'DROP VIEW IF EXISTS "{name}"')
            elif obj_type == "table":
                conn.execute(f'DROP TABLE IF EXISTS "{name}"')
            elif obj_type == "index":
                conn.execute(f'DROP INDEX IF EXISTS "{name}"')
    finally:
        if was_enabled:
            _set_foreign_keys(conn, enabled=True)
    conn.commit()


def table_exists(conn: LedgerConnection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def table_columns(conn: LedgerConnection, table_name: str) -> set[str]:
    if not table_exists(conn, table_name):
        return set()
    rows = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    return {str(row[1]) for row in rows}


def require_ledger_columns(conn: LedgerConnection) -> None:
    required = {
        "calls": {"identity", "source_identity", "content", "created_at", "extra_json"},
        "responses": {
            "identity",
            "final_step",
            "result_key",
            "result_kind",
            "status",
            "content",
            "fail_message",
            "raw_json",
            "created_at",
        },
        "exports": {
            "export_id",
            "response_identity",
            "destination",
            "export_mode",
            "target_slug",
            "target_path",
            "exported_at",
            "export_message",
            "consumer_json",
            "created_at",
        },
    }
    missing: list[str] = []
    for table_name, expected in required.items():
        actual = table_columns(conn, table_name)
        for column_name in sorted(expected - actual):
            missing.append(f"{table_name}.{column_name}")
    if missing:
        raise RuntimeError("ledger schema is incomplete; missing columns: " + ", ".join(missing))


CALLS: ColumnSpec = {
    "identity": "TEXT PRIMARY KEY NOT NULL UNIQUE CHECK (length(identity) = 26)",
    "source_identity": "TEXT NOT NULL",
    "content": "TEXT NOT NULL",
    "created_at": "INTEGER NOT NULL",
    "extra_json": "TEXT NOT NULL DEFAULT '{}'",
}


RESPONSES: ColumnSpec = {
    # Primary key is the call identity. This is deliberate: calls.identity joins
    # directly to responses.identity.
    "identity": "TEXT PRIMARY KEY NOT NULL UNIQUE CHECK (length(identity) = 26)",
    "final_step": "INTEGER NOT NULL CHECK (final_step > 0)",
    "result_key": "TEXT NOT NULL",
    "result_kind": "TEXT NOT NULL CHECK (result_kind IN ('response', 'transform', 'retrieval', 'result', 'failure'))",
    "status": "TEXT NOT NULL CHECK (status IN ('success', 'failure'))",
    "content": "TEXT",
    "fail_message": "TEXT",
    "raw_json": "TEXT NOT NULL",
    "created_at": "INTEGER NOT NULL",
    "__constraints__": [
        "FOREIGN KEY(identity) REFERENCES calls(identity) ON DELETE CASCADE",
    ],
}


EXPORTS: ColumnSpec = {
    "export_id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "response_identity": "TEXT NOT NULL CHECK (length(response_identity) = 26)",
    "destination": "TEXT",
    "export_mode": "TEXT NOT NULL DEFAULT 'manual'",
    "target_slug": "TEXT",
    "target_path": "TEXT",
    "exported_at": "INTEGER NOT NULL",
    "export_message": "TEXT",
    "consumer_json": "TEXT",
    "created_at": "INTEGER NOT NULL",
    "__constraints__": [
        "FOREIGN KEY(response_identity) REFERENCES responses(identity) ON DELETE CASCADE",
    ],
}


LEDGER_TABLES = {
    "calls": CALLS,
    "responses": RESPONSES,
    "exports": EXPORTS,
}


LEDGER_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_calls_source_identity ON calls(source_identity)",
    "CREATE INDEX IF NOT EXISTS idx_calls_created_at ON calls(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_responses_status ON responses(status)",
    "CREATE INDEX IF NOT EXISTS idx_responses_created_at ON responses(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_responses_result_key ON responses(result_key)",
    "CREATE INDEX IF NOT EXISTS idx_exports_response_identity ON exports(response_identity)",
    "CREATE INDEX IF NOT EXISTS idx_exports_exported_at ON exports(exported_at)",
    "CREATE INDEX IF NOT EXISTS idx_exports_created_at ON exports(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_exports_target_slug ON exports(target_slug)",
)


def ensure_ledger_views(conn: LedgerConnection) -> None:
    for statement in CREATE_LEDGER_VIEWS_SQL:
        conn.execute(statement)
    conn.commit()


def reset_ledger_views(conn: LedgerConnection) -> None:
    drop_views(conn, LEDGER_VIEW_NAMES)
    ensure_ledger_views(conn)


def _migrate_legacy_calls_table(conn: LedgerConnection) -> None:
    """Replace the pre-four-field calls table without losing ledger rows."""

    actual = table_columns(conn, "calls")
    current = set(CALLS)
    if not actual or actual == current:
        return

    legacy = {
        "identity",
        "source_identity",
        "plan_key",
        "content",
        "created_at",
        "blob_json",
    }
    if actual != legacy:
        raise RuntimeError(
            "unsupported calls ledger schema: "
            f"columns={tuple(sorted(actual))!r}"
        )

    was_enabled = _foreign_keys_enabled(conn)
    if was_enabled:
        _set_foreign_keys(conn, enabled=False)
    try:
        conn.execute("DROP TABLE IF EXISTS calls_four_field")
        conn.execute(create_table_sql("calls_four_field", CALLS))
        conn.execute(
            """
            INSERT INTO calls_four_field (
                identity, source_identity, content, created_at, extra_json
            )
            SELECT
                identity, source_identity, content, created_at, blob_json
            FROM calls
            """
        )
        conn.execute("DROP TABLE calls")
        conn.execute("ALTER TABLE calls_four_field RENAME TO calls")
        conn.commit()
    finally:
        if was_enabled:
            _set_foreign_keys(conn, enabled=True)


def ensure_ledger_schema(conn: LedgerConnection) -> None:
    drop_views(conn, LEDGER_VIEW_NAMES)
    _migrate_legacy_calls_table(conn)
    ensure_schema(conn, LEDGER_TABLES, LEDGER_INDEXES, CREATE_LEDGER_VIEWS_SQL)
    require_ledger_columns(conn)


def reset_ledger_schema(conn: LedgerConnection) -> None:
    drop_user_objects(conn)
    ensure_ledger_schema(conn)


def ensure_all_schemas(conn: LedgerConnection) -> None:
    ensure_ledger_schema(conn)


def reset_all_schemas(conn: LedgerConnection) -> None:
    reset_ledger_schema(conn)


__all__ = [
    "CALLS",
    "RESPONSES",
    "EXPORTS",
    "LEDGER_TABLES",
    "LEDGER_INDEXES",
    "ColumnSpec",
    "create_table_sql",
    "drop_tables",
    "drop_user_objects",
    "drop_views",
    "require_ledger_columns",
    "table_columns",
    "table_exists",
    "ensure_all_schemas",
    "ensure_ledger_schema",
    "ensure_ledger_views",
    "ensure_schema",
    "reset_all_schemas",
    "reset_ledger_schema",
    "reset_ledger_views",
]
