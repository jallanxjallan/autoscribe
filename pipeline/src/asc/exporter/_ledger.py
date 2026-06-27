"""SQLite ledger queries used by the exporter package.

The exporter is a read/writeback boundary over Scrivener's ledger tables.  It
should not import the Scrivener daemon writers or any old ``records`` package;
those modules are runtime write boundaries.  These helpers speak directly to
Scrivener's current ledger schema:

- calls(identity, source_identity, source_json, created_at)
- steps(identity, step_number, result_key, status, content, fail_message, raw_json, created_at)
- exports(identity, source_identity, final_step, result_key, exported_at, export_message, created_at)
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from asc.redis.key import RedisKey
from asc.scrivener.connect import LedgerConnection
from asc.scrivener.schema import require_ledger_columns
from asc.scrivener.util import timestamp_now


DEFAULT_EXPORT_MESSAGE = "writeback"


def pending_export_rows(
    *,
    conn: LedgerConnection,
    source_identity: str | None = None,
) -> list[dict[str, Any]]:
    """Return unexported terminal result rows.

    ``source_identity`` is the source document/record identity that the enqueue
    manifest called ``record_identity``.  Older exporter code called this a
    prompt slug in some UI text, but the ledger contract now names it directly.
    """

    require_ledger_columns(conn)
    _require_unique_pending_sources(conn)

    where = "WHERE e.exported_at IS NULL"
    values: tuple[Any, ...] = ()
    if source_identity is not None:
        where += " AND COALESCE(c.source_identity, e.source_identity) = ?"
        values = (source_identity,)

    rows = conn.execute(
        f"""
        SELECT
            COALESCE(c.source_identity, e.source_identity) AS source_identity,
            COALESCE(c.source_identity, e.source_identity) AS record_identity,
            e.identity AS call_identity,
            e.final_step AS final_step,
            e.result_key AS result_key,
            e.result_key AS result_identity,
            e.created_at AS created_at
        FROM exports AS e
        LEFT JOIN calls AS c
          ON c.identity = e.identity
        {where}
        ORDER BY COALESCE(c.source_identity, e.source_identity) ASC, e.created_at ASC, e.identity ASC
        """,
        values,
    ).fetchall()
    return [_row_dict(row) for row in rows]


def extracted_result_row(*, conn: LedgerConnection, call_identity: str) -> dict[str, Any] | None:
    """Return one exportable terminal result row by call identity."""

    require_ledger_columns(conn)
    identity = _call_identity(call_identity)
    row = conn.execute(
        """
        SELECT
            c.source_identity AS source_identity,
            c.source_identity AS record_identity,
            c.identity AS call_identity,
            e.final_step AS final_step,
            e.result_key AS result_key,
            e.result_key AS result_identity,
            s.content AS content,
            s.raw_json AS raw_json,
            c.source_json AS source_json,
            c.created_at AS call_created_at,
            s.created_at AS step_created_at,
            e.created_at AS export_created_at,
            e.exported_at AS exported_at,
            e.export_message AS export_message
        FROM calls AS c
        JOIN exports AS e
          ON e.identity = c.identity
        JOIN steps AS s
          ON s.identity = e.identity
         AND s.step_number = e.final_step
        WHERE c.identity = ?
        """,
        (identity,),
    ).fetchone()
    if row is None:
        return None
    data = _row_dict(row)
    data["source"] = _safe_json(data.get("source_json"))
    data["result"] = _safe_json(data.get("raw_json"))
    return data


def mark_exported(
    *,
    conn: LedgerConnection,
    result_identity: str,
    export_message: str = DEFAULT_EXPORT_MESSAGE,
) -> int:
    """Mark the export custody row complete.

    The CLI historically passed ``result_identity``.  The current ledger stores
    one row per call and points at the terminal ``result_key``, so accept either
    a full result key (``response:<call>:<step>``) or the bare call identity.
    """

    require_ledger_columns(conn)
    identity = _call_identity(result_identity)
    cursor = conn.execute(
        """
        UPDATE exports
        SET
            exported_at = ?,
            export_message = ?
        WHERE identity = ?
          AND exported_at IS NULL
        """,
        (int(timestamp_now()), export_message, identity),
    )
    conn.commit()
    if cursor.rowcount == 0:
        raise ValueError(f"no pending export row for result/call {result_identity}")
    return int(cursor.rowcount)


def _require_unique_pending_sources(conn: LedgerConnection) -> None:
    rows = conn.execute(
        """
        SELECT COALESCE(c.source_identity, e.source_identity) AS source_identity, COUNT(*) AS pending_count
        FROM exports AS e
        LEFT JOIN calls AS c
          ON c.identity = e.identity
        WHERE e.exported_at IS NULL
        GROUP BY COALESCE(c.source_identity, e.source_identity)
        HAVING COUNT(*) > 1
        ORDER BY COALESCE(c.source_identity, e.source_identity) ASC
        """
    ).fetchall()
    if not rows:
        return
    details = ", ".join(f"{row['source_identity']}={row['pending_count']}" for row in rows)
    raise ValueError(f"multiple pending exports for source_identity: {details}")


def _call_identity(value: object) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError("result/call identity must not be empty")
    if ":" in text:
        return RedisKey(text).identity
    return text


def _row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)
    return {key: row[key] for key in row.keys()}


def _safe_json(value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return value


__all__ = [
    "DEFAULT_EXPORT_MESSAGE",
    "extracted_result_row",
    "mark_exported",
    "pending_export_rows",
]
