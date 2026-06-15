from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from asc.scrivener.connect import connect


TABLE_NAMES = ("calls", "steps", "results", "exports")


@dataclass(frozen=True, slots=True)
class TableCount:
    table: str
    rows: int


def table_counts() -> tuple[TableCount, ...]:
    with connect() as conn:
        return tuple(
            TableCount(table=name, rows=_count(conn, name))
            for name in TABLE_NAMES
        )


def recent_calls(*, limit: int = 20) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                c.call,
                c.plan,
                c.record_identity AS source_identifier,
                c.record_identity AS source_slug,
                c.created_at,
                COUNT(s.step_id) AS steps,
                SUM(CASE WHEN s.status = 'pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN s.status = 'running' THEN 1 ELSE 0 END) AS running,
                SUM(CASE WHEN s.status = 'completed' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN s.status = 'failed' THEN 1 ELSE 0 END) AS failed
            FROM calls AS c
            LEFT JOIN steps AS s
                ON s.call = c.call
            GROUP BY c.call
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
        where = f"WHERE s.status IN ({', '.join('?' for _ in statuses)})"
        params.extend(statuses)

    params.append(limit)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                s.call,
                s.step_number,
                s.status,
                s.handler,
                s.engine,
                s.input_key,
                s.output_key,
                s.created_at,
                s.started_at,
                s.completed_at,
                s.fail_message
            FROM steps AS s
            {where}
            ORDER BY s.created_at DESC, s.call ASC, s.step_number ASC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        return [_row_dict(row) for row in rows]


def recent_results(*, limit: int = 30) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                r.result,
                r.call,
                r.terminal_step_id,
                r.created_at,
                CASE WHEN e.result IS NULL THEN 0 ELSE 1 END AS exported,
                e.created_at AS exported_at
            FROM results AS r
            LEFT JOIN exports AS e
                ON e.result = r.result
            ORDER BY r.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_row_dict(row) for row in rows]


def recent_exports(*, limit: int = 30) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                e.result,
                r.call,
                e.export_message,
                e.created_at
            FROM exports AS e
            LEFT JOIN results AS r
                ON r.result = e.result
            ORDER BY e.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_row_dict(row) for row in rows]


def pending_work(*, limit: int = 50) -> list[dict[str, Any]]:
    return recent_steps(limit=limit, statuses=("pending", "running", "failed"))


def show_call(call: str) -> dict[str, Any]:
    with connect() as conn:
        call_row = conn.execute(
            "SELECT * FROM calls WHERE call = ?",
            (call,),
        ).fetchone()
        if call_row is None:
            raise KeyError(f"call not found: {call}")

        step_rows = conn.execute(
            """
            SELECT *
            FROM steps
            WHERE call = ?
            ORDER BY step_number ASC
            """,
            (call,),
        ).fetchall()
        result_row = conn.execute(
            "SELECT * FROM results WHERE call = ?",
            (call,),
        ).fetchone()
        export_row = None
        if result_row is not None:
            export_row = conn.execute(
                "SELECT * FROM exports WHERE result = ?",
                (result_row["result"],),
            ).fetchone()

    raw = _safe_json(call_row["raw_json"])
    return {
        "call": _row_dict(call_row),
        "raw": raw,
        "steps": [_row_dict(row) for row in step_rows],
        "result": _row_dict(result_row) if result_row is not None else None,
        "export": _row_dict(export_row) if export_row is not None else None,
    }


def show_step(call: str, step_number: int) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM steps
            WHERE call = ? AND step_number = ?
            """,
            (call, step_number),
        ).fetchone()
        if row is None:
            raise KeyError(f"step not found: {call} step {step_number}")
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
    "pending_work",
    "recent_calls",
    "recent_exports",
    "recent_results",
    "recent_steps",
    "show_call",
    "show_step",
    "table_counts",
]
