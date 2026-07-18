from dataclasses import dataclass
import json
from typing import Any

from asc.ledger.connect import connect


TABLE_NAMES = ("calls", "responses", "exports")


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
                r.status AS response_status,
                r.final_step,
                r.result_key,
                r.created_at AS response_created_at,
                COUNT(e.export_id) AS exports
            FROM calls AS c
            LEFT JOIN responses AS r
                ON r.identity = c.identity
            LEFT JOIN exports AS e
                ON e.response_identity = c.identity
            GROUP BY c.identity
            ORDER BY c.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_row_dict(row) for row in rows]


def recent_responses(*, limit: int = 50, statuses: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    where = ""
    params: list[Any] = []
    if statuses:
        where = f"WHERE r.status IN ({', '.join('?' for _ in statuses)})"
        params.extend(statuses)
    params.append(limit)

    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                r.*,
                c.source_identity
            FROM responses AS r
            JOIN calls AS c
                ON c.identity = r.identity
            {where}
            ORDER BY r.created_at DESC, r.identity ASC
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
                e.export_id,
                e.response_identity,
                c.source_identity,
                e.destination,
                e.export_mode,
                e.target_slug,
                e.target_path,
                e.exported_at,
                e.export_message,
                e.consumer_json,
                e.created_at
            FROM exports AS e
            JOIN calls AS c
                ON c.identity = e.response_identity
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
                c.source_identity AS record_identity,
                r.identity AS call_identity,
                r.final_step,
                r.result_key,
                r.created_at
            FROM responses AS r
            JOIN calls AS c
                ON c.identity = r.identity
            LEFT JOIN exports AS e
                ON e.response_identity = r.identity
            WHERE r.status = 'success'
              AND e.response_identity IS NULL
            ORDER BY r.created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_row_dict(row) for row in rows]


def pending_export_for_source(source_identity: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
                c.source_identity AS record_identity,
                r.identity AS call_identity,
                r.final_step,
                r.result_key,
                r.created_at
            FROM responses AS r
            JOIN calls AS c
                ON c.identity = r.identity
            LEFT JOIN exports AS e
                ON e.response_identity = r.identity
            WHERE c.source_identity = ?
              AND r.status = 'success'
              AND e.response_identity IS NULL
            ORDER BY r.created_at ASC, r.identity ASC
            LIMIT 1
            """,
            (source_identity,),
        ).fetchone()
    return _row_dict(row) if row is not None else None


def recent_results(*, limit: int = 30) -> list[dict[str, Any]]:
    return recent_responses(limit=limit)


def pending_work(*, limit: int = 50) -> list[dict[str, Any]]:
    failed = recent_responses(limit=limit, statuses=("failure",))
    if len(failed) >= limit:
        return failed[:limit]
    exports = pending_exports(limit=limit - len(failed))
    for row in exports:
        row.setdefault("status", "pending_export")
    return failed + exports


def show_call(identity: str) -> dict[str, Any]:
    with connect() as conn:
        call_row = conn.execute("SELECT * FROM calls WHERE identity = ?", (identity,)).fetchone()
        if call_row is None:
            raise KeyError(f"call not found: {identity}")
        response_row = conn.execute("SELECT * FROM responses WHERE identity = ?", (identity,)).fetchone()
        export_rows = conn.execute(
            "SELECT * FROM exports WHERE response_identity = ? ORDER BY exported_at ASC, export_id ASC",
            (identity,),
        ).fetchall()

    return {
        "call": _row_dict(call_row),
        "source": _safe_json(call_row["blob_json"]),
        "response": _row_dict(response_row) if response_row is not None else None,
        "exports": [_row_dict(row) for row in export_rows],
    }


def show_response(identity: str) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM responses
            WHERE identity = ?
            """,
            (identity,),
        ).fetchone()
        if row is None:
            raise KeyError(f"response not found: {identity}")
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
    "pending_export_for_source",
    "pending_exports",
    "pending_work",
    "recent_calls",
    "recent_exports",
    "recent_results",
    "recent_responses",
    "show_call",
    "show_response",
    "table_counts",
]
