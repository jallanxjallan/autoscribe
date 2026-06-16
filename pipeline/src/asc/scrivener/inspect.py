from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from asc.scrivener.connect import connect


TABLE_NAMES = ("calls", "steps", "exports")


@dataclass(frozen=True, slots=True)
class TableCount:
    table: str
    rows: int


def table_counts() -> tuple[TableCount, ...]:
    with connect() as conn:
        return tuple(TableCount(table=name, rows=_count(conn, name)) for name in TABLE_NAMES)


def recent_calls(*, limit: int = 20) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                c.identity,
                c.source_identity,
                c.created_at,
                COUNT(s.step_number) AS steps,
                SUM(CASE WHEN s.status = 'completed' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN s.status = 'failed' THEN 1 ELSE 0 END) AS failed,
                CASE WHEN e.identity IS NULL THEN 0 ELSE 1 END AS export_ready,
                e.exported_at
            FROM calls AS c
            LEFT JOIN steps AS s
                ON s.identity = c.identity
            LEFT JOIN exports AS e
                ON e.identity = c.identity
            GROUP BY c.identity
            ORDER BY c.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_row_dict(row) for row in rows]


def recent_steps(*, limit: int = 50, statuses: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    where = ""
    params: list[Any] = []
    if statuses:
        where = f"WHERE status IN ({', '.join('?' for _ in statuses)})"
        params.extend(statuses)
    params.append(limit)

    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM steps
            {where}
            ORDER BY created_at DESC, identity ASC, step_number ASC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        return [_row_dict(row) for row in rows]


def recent_exports(*, limit: int = 30) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                e.identity,
                c.source_identity,
                e.final_step,
                e.result_key,
                e.created_at,
                e.exported_at,
                e.export_message
            FROM exports AS e
            LEFT JOIN calls AS c
                ON c.identity = e.identity
            ORDER BY e.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_row_dict(row) for row in rows]


def pending_exports(*, limit: int = 50) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                e.identity,
                c.source_identity,
                e.final_step,
                e.result_key,
                e.created_at
            FROM exports AS e
            JOIN calls AS c
                ON c.identity = e.identity
            WHERE e.exported_at IS NULL
            ORDER BY e.created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_row_dict(row) for row in rows]


def pending_work(*, limit: int = 50) -> list[dict[str, Any]]:
    """Legacy CLI name.

    Scrivener no longer tracks pending/running workflow state.  The nearest
    useful inspection surface is failed ledgered steps plus pending exports.
    """

    failed = recent_steps(limit=limit, statuses=("failed",))
    if len(failed) >= limit:
        return failed[:limit]
    exports = pending_exports(limit=limit - len(failed))
    for row in exports:
        row.setdefault("status", "pending_export")
    return failed + exports


def recent_results(*, limit: int = 30) -> list[dict[str, Any]]:
    """Legacy CLI name.

    The results table was intentionally removed.  Exports now point directly at
    the terminal step result, so recent exports are the result inspection view.
    """

    return recent_exports(limit=limit)


def show_call(identity: str) -> dict[str, Any]:
    with connect() as conn:
        call_row = conn.execute("SELECT * FROM calls WHERE identity = ?", (identity,)).fetchone()
        if call_row is None:
            raise KeyError(f"call not found: {identity}")
        step_rows = conn.execute(
            "SELECT * FROM steps WHERE identity = ? ORDER BY step_number ASC",
            (identity,),
        ).fetchall()
        export_row = conn.execute("SELECT * FROM exports WHERE identity = ?", (identity,)).fetchone()

    return {
        "call": _row_dict(call_row),
        "source": _safe_json(call_row["source_json"]),
        "steps": [_row_dict(row) for row in step_rows],
        "export": _row_dict(export_row) if export_row is not None else None,
    }


def show_step(identity: str, step_number: int) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM steps
            WHERE identity = ?
              AND step_number = ?
            """,
            (identity, step_number),
        ).fetchone()
        if row is None:
            raise KeyError(f"step not found: {identity} step {step_number}")
    data = _row_dict(row)
    data["raw"] = _safe_json(data.get("raw_json"))
    return data


def _count(conn: Any, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return int(row[0])


def _row_dict(row: Any | None) -> dict[str, Any]:
    if row is None:
        return {}
    return {key: row[key] for key in row.keys()}


def _safe_json(value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return value


__all__ = [
    "TableCount",
    "pending_exports",
    "pending_work",
    "recent_calls",
    "recent_exports",
    "recent_results",
    "recent_steps",
    "show_call",
    "show_step",
    "table_counts",
]
