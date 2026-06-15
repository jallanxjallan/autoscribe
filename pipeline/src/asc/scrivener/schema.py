from __future__ import annotations

from collections.abc import Iterable

from asc.scrivener.connect import LedgerConnection
from asc.scrivener.views import CREATE_LEDGER_VIEWS_SQL, LEDGER_VIEW_NAMES

ColumnSpec = dict[str, str | list[str]]


def create_table_sql(name: str, columns: ColumnSpec) -> str:
    column_defs: list[str] = []
    constraints: list[str] = []

    for col, spec in columns.items():
        if col == "__constraints__":
            constraints.extend(spec)  # type: ignore[arg-type]
        else:
            column_defs.append(f"{col} {spec}")

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

    for stmt in indexes:
        conn.execute(stmt)

    for stmt in views:
        conn.execute(stmt)

    conn.commit()


def _foreign_keys_enabled(conn: LedgerConnection) -> bool:
    row = conn.execute("PRAGMA foreign_keys").fetchone()
    return bool(row[0]) if row is not None else True


def _set_foreign_keys(conn: LedgerConnection, *, enabled: bool) -> None:
    value = "ON" if enabled else "OFF"
    conn.execute(f"PRAGMA foreign_keys = {value}")


def drop_views(conn: LedgerConnection, view_names: Iterable[str]) -> None:
    for view_name in view_names:
        conn.execute(f"DROP VIEW IF EXISTS {view_name}")
    conn.commit()


def drop_tables(conn: LedgerConnection, table_names: Iterable[str]) -> None:
    was_enabled = _foreign_keys_enabled(conn)
    try:
        if was_enabled:
            _set_foreign_keys(conn, enabled=False)

        for table_name in table_names:
            conn.execute(f"DROP TABLE IF EXISTS {table_name}")
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


def add_column_if_missing(
    conn: LedgerConnection,
    *,
    table_name: str,
    column_name: str,
    column_sql: str,
) -> None:
    if column_name not in table_columns(conn, table_name):
        conn.execute(f'ALTER TABLE "{table_name}" ADD COLUMN {column_name} {column_sql}')


def migrate_ledger_schema(conn: LedgerConnection) -> None:
    """Bring older development ledgers up to the current column names.

    SQLite's CREATE TABLE IF NOT EXISTS does not repair an existing table whose
    columns came from an older architecture.  This migration is intentionally
    small and explicit: it only adds columns Scrivener currently writes or the
    ledger views currently read.  It does not make workflow decisions and it
    does not drop data.
    """

    if table_exists(conn, "calls"):
        call_cols = table_columns(conn, "calls")
        if "record_identity" not in call_cols:
            conn.execute('ALTER TABLE "calls" ADD COLUMN record_identity TEXT')
            call_cols = table_columns(conn, "calls")
            if "prompt_slug" in call_cols:
                conn.execute(
                    """
                    UPDATE calls
                    SET record_identity = prompt_slug
                    WHERE record_identity IS NULL
                       OR record_identity = ''
                    """
                )
        add_column_if_missing(conn, table_name="calls", column_name="plan", column_sql="TEXT")
        add_column_if_missing(conn, table_name="calls", column_name="raw_json", column_sql="TEXT")
        add_column_if_missing(conn, table_name="calls", column_name="created_at", column_sql="INTEGER")

    if table_exists(conn, "steps"):
        add_column_if_missing(conn, table_name="steps", column_name="input_key", column_sql="TEXT")
        add_column_if_missing(conn, table_name="steps", column_name="output_key", column_sql="TEXT")
        add_column_if_missing(conn, table_name="steps", column_name="started_at", column_sql="INTEGER")
        add_column_if_missing(conn, table_name="steps", column_name="completed_at", column_sql="INTEGER")
        add_column_if_missing(conn, table_name="steps", column_name="prompt_tokens", column_sql="INTEGER")
        add_column_if_missing(conn, table_name="steps", column_name="completion_tokens", column_sql="INTEGER")
        add_column_if_missing(conn, table_name="steps", column_name="total_tokens", column_sql="INTEGER")

    if table_exists(conn, "results"):
        add_column_if_missing(conn, table_name="results", column_name="result", column_sql="TEXT")
        add_column_if_missing(conn, table_name="results", column_name="call", column_sql="TEXT")
        add_column_if_missing(conn, table_name="results", column_name="terminal_step_id", column_sql="INTEGER")
        add_column_if_missing(conn, table_name="results", column_name="created_at", column_sql="INTEGER")

    if table_exists(conn, "exports"):
        add_column_if_missing(conn, table_name="exports", column_name="result", column_sql="TEXT")
        add_column_if_missing(conn, table_name="exports", column_name="export_message", column_sql="TEXT")
        add_column_if_missing(conn, table_name="exports", column_name="created_at", column_sql="INTEGER")

    conn.commit()


def require_ledger_columns(conn: LedgerConnection) -> None:
    required = {
        "calls": {"call", "plan", "record_identity", "raw_json", "created_at"},
        "results": {"result", "call", "terminal_step_id", "created_at"},
        "exports": {"result", "export_message", "created_at"},
    }
    missing: list[str] = []
    for table_name, expected in required.items():
        actual = table_columns(conn, table_name)
        for column_name in sorted(expected - actual):
            missing.append(f"{table_name}.{column_name}")
    if missing:
        raise RuntimeError(
            "ledger schema is incomplete; missing columns: " + ", ".join(missing)
        )


CALLS: ColumnSpec = {
    "call": "TEXT PRIMARY KEY NOT NULL UNIQUE CHECK (length(call) = 26)",
    "plan": "TEXT NOT NULL",
    "record_identity": "TEXT NOT NULL",
    "raw_json": "TEXT NOT NULL",
    "created_at": "INTEGER NOT NULL",
}


STEPS: ColumnSpec = {
    "step_id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "call": "TEXT NOT NULL CHECK (length(call) = 26)",
    "step_number": "INTEGER NOT NULL CHECK (step_number > 0)",
    "handler": "TEXT NOT NULL",
    "engine": "TEXT NOT NULL",
    "status": "TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed'))",
    "prompt": "TEXT NOT NULL",
    "response": "TEXT",
    "fail_message": "TEXT",
    "raw_json": "TEXT NOT NULL",
    "input_key": "TEXT",
    "output_key": "TEXT",
    "created_at": "INTEGER NOT NULL",
    "started_at": "INTEGER",
    "completed_at": "INTEGER",
    "prompt_tokens": "INTEGER",
    "completion_tokens": "INTEGER",
    "total_tokens": "INTEGER",
    "__constraints__": [
        "FOREIGN KEY(call) REFERENCES calls(call) ON DELETE CASCADE",
        "UNIQUE(call, step_number)",
    ],
}


RESULTS: ColumnSpec = {
    "result": "TEXT PRIMARY KEY NOT NULL UNIQUE CHECK (length(result) = 26)",
    "call": "TEXT NOT NULL UNIQUE CHECK (length(call) = 26)",
    "terminal_step_id": "INTEGER NOT NULL UNIQUE",
    "created_at": "INTEGER NOT NULL",
    "__constraints__": [
        "FOREIGN KEY(call) REFERENCES calls(call) ON DELETE CASCADE",
        "FOREIGN KEY(terminal_step_id) REFERENCES steps(step_id) ON DELETE CASCADE",
    ],
}


EXPORTS: ColumnSpec = {
    "result": "TEXT PRIMARY KEY NOT NULL CHECK (length(result) = 26)",
    "export_message": "TEXT NOT NULL",
    "created_at": "INTEGER NOT NULL",
    "__constraints__": [
        "FOREIGN KEY(result) REFERENCES results(result) ON DELETE CASCADE",
    ],
}


LEDGER_TABLES = {
    "calls": CALLS,
    "steps": STEPS,
    "results": RESULTS,
    "exports": EXPORTS,
}


LEDGER_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_calls_plan ON calls(plan)",
    "CREATE INDEX IF NOT EXISTS idx_calls_record_identity ON calls(record_identity)",
    "CREATE INDEX IF NOT EXISTS idx_calls_created_at ON calls(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_steps_call ON steps(call)",
    "CREATE INDEX IF NOT EXISTS idx_steps_call_step_number ON steps(call, step_number)",
    "CREATE INDEX IF NOT EXISTS idx_steps_status ON steps(status)",
    "CREATE INDEX IF NOT EXISTS idx_steps_completed_at ON steps(completed_at)",
    "CREATE INDEX IF NOT EXISTS idx_results_call ON results(call)",
    "CREATE INDEX IF NOT EXISTS idx_results_terminal_step_id ON results(terminal_step_id)",
    "CREATE INDEX IF NOT EXISTS idx_results_created_at ON results(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_exports_created_at ON exports(created_at)",
)


def ensure_ledger_views(conn: LedgerConnection) -> None:
    for statement in CREATE_LEDGER_VIEWS_SQL:
        conn.execute(statement)
    conn.commit()


def reset_ledger_views(conn: LedgerConnection) -> None:
    drop_views(conn, LEDGER_VIEW_NAMES)
    ensure_ledger_views(conn)


def ensure_ledger_schema(conn: LedgerConnection) -> None:
    drop_views(conn, LEDGER_VIEW_NAMES)
    ensure_schema(conn, LEDGER_TABLES)
    migrate_ledger_schema(conn)
    require_ledger_columns(conn)
    ensure_schema(conn, {}, LEDGER_INDEXES, CREATE_LEDGER_VIEWS_SQL)


def reset_ledger_schema(conn: LedgerConnection) -> None:
    drop_views(conn, LEDGER_VIEW_NAMES)
    drop_tables(conn, ("exports", "results", "steps", "calls"))
    ensure_ledger_schema(conn)


def ensure_all_schemas(conn: LedgerConnection) -> None:
    ensure_ledger_schema(conn)


def reset_all_schemas(conn: LedgerConnection) -> None:
    reset_ledger_schema(conn)


__all__ = [
    "CALLS",
    "STEPS",
    "RESULTS",
    "EXPORTS",
    "LEDGER_TABLES",
    "LEDGER_INDEXES",
    "ColumnSpec",
    "create_table_sql",
    "drop_tables",
    "drop_user_objects",
    "drop_views",
    "migrate_ledger_schema",
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
