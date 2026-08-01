"""Export terminal result records from the reduced ledger."""

from __future__ import annotations

import json
from typing import Any, TextIO

from asc.ledger.connect import LedgerConnection
from asc.ledger.records.export import insert_export_record_with_connection
from asc.ledger.records.result import (
    read_extract_result_record_by_call_identity_with_connection,
    read_pending_result_export_records_with_connection,
)
from asc.ledger.schema import ensure_ledger_schema
from asc.ledger.util import timestamp_now


SELECT_LATEST_RESULT_BY_SOURCE_IDENTITY_SQL = """
    SELECT
        c.identity AS identity,
        c.source_identity AS source_identity,
        c.extra_json AS source_json,
        c.created_at AS call_created_at,
        r.final_step AS step_number,
        r.result_key AS result_key,
        r.content AS content,
        r.raw_json AS raw_json,
        r.created_at AS step_created_at,
        NULL AS export_created_at,
        NULL AS exported_at,
        NULL AS export_message
    FROM calls AS c
    JOIN results AS r
        ON r.identity = c.identity
    WHERE c.source_identity = ?
      AND r.status = 'success'
    ORDER BY r.created_at DESC, c.created_at DESC, c.identity DESC
    LIMIT 1
"""



def write_extracted_result_record(
    *,
    call_identity: str,
    conn: LedgerConnection,
    sink: TextIO,
) -> None:
    """Emit one call/result extraction row as NDJSON."""

    ensure_ledger_schema(conn)
    row = read_extract_result_record_by_call_identity_with_connection(
        conn=conn,
        call_identity=_identity_part(call_identity),
    )
    if row is None:
        raise ValueError(f"no terminal result for call identity: {call_identity}")
    _write_ndjson(row, sink=sink)


def write_pending_result_records(
    *,
    conn: LedgerConnection,
    sink: TextIO,
) -> None:
    """Emit all pending successful results as NDJSON."""

    ensure_ledger_schema(conn)
    for row in read_pending_result_export_records_with_connection(conn=conn):
        extracted = read_extract_result_record_by_call_identity_with_connection(
            conn=conn,
            call_identity=str(row["call_identity"]),
        )
        if extracted is not None:
            _write_ndjson(extracted, sink=sink)


def write_result_records_by_slugs(
    *,
    slugs: list[str],
    conn: LedgerConnection,
    sink: TextIO,
    export_message: str = "retrieve-results",
) -> list[str]:
    """Emit the latest successful result available for each source slug.

    Slugs are handled independently. A missing or unfinished result does not
    prevent completed results for the other slugs from being emitted. Each
    emitted record receives a new row in ``exports``; prior export receipts do
    not affect selection.

    Return the slugs for which no successful terminal result currently exists.
    """

    ensure_ledger_schema(conn)
    cleaned = list(dict.fromkeys(slug.strip() for slug in slugs if slug.strip()))
    if not cleaned:
        raise ValueError("at least one slug is required")

    missing: list[str] = []
    for slug in cleaned:
        row = conn.execute(SELECT_LATEST_RESULT_BY_SOURCE_IDENTITY_SQL, (slug,)).fetchone()
        if row is None:
            missing.append(slug)
            continue

        data = _normalize_extract_row(row)
        insert_export_record_with_connection(
            conn=conn,
            result_identity=str(data["identity"]),
            export_message=export_message,
            export_mode="retrieve-results",
        )
        conn.commit()
        _write_ndjson(data, sink=sink)

    return missing



def mark_result_exported(
    *,
    result_identity: str,
    conn: LedgerConnection,
    export_message: str = "writeback",
) -> None:
    """Record a delivery receipt for a terminal result."""

    ensure_ledger_schema(conn)
    insert_export_record_with_connection(
        conn=conn,
        result_identity=result_identity,
        export_message=export_message,
        export_mode="writeback",
    )


def reset_result_exported(
    *,
    identities: list[str],
    conn: LedgerConnection,
    export_message: str = "reset",
) -> int:
    """Delete export receipts so matching results become pending again.

    Under the reduced ledger model, ``exports`` is a receipt table. There is no
    ``exported_at = 0`` placeholder row to preserve; pending means no receipt.
    ``export_message`` is retained only for the old CLI signature.
    """

    ensure_ledger_schema(conn)
    result_identities = _resolve_result_identities(conn=conn, identities=identities)
    if not result_identities:
        return 0

    placeholders = ", ".join("?" for _ in result_identities)
    cursor = conn.execute(
        f"DELETE FROM exports WHERE result_identity IN ({placeholders})",
        tuple(sorted(result_identities)),
    )
    conn.commit()
    return int(cursor.rowcount if cursor.rowcount is not None else 0)


def _resolve_result_identities(
    *,
    conn: LedgerConnection,
    identities: list[str],
) -> set[str]:
    resolved: set[str] = set()
    for value in identities:
        cleaned = value.strip()
        if not cleaned:
            continue
        identity = _identity_part(cleaned)

        # Direct call/result identity.
        row = conn.execute("SELECT identity FROM results WHERE identity = ?", (identity,)).fetchone()
        if row is not None:
            resolved.add(str(row[0]))
            continue

        # Terminal result key stored on the result row.
        row = conn.execute("SELECT identity FROM results WHERE result_key = ?", (cleaned,)).fetchone()
        if row is not None:
            resolved.add(str(row[0]))
            continue

        # Source identity / slug.
        rows = conn.execute(
            """
            SELECT r.identity
            FROM results AS r
            JOIN calls AS c
                ON c.identity = r.identity
            WHERE c.source_identity = ?
            """,
            (cleaned,),
        ).fetchall()
        resolved.update(str(row[0]) for row in rows)
    return resolved


def _identity_part(value: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError("identity must be non-empty")
    parts = text.split(":")
    if len(parts) >= 2:
        return parts[1]
    return text


def _normalize_extract_row(row: Any) -> dict[str, Any]:
    data = {key: row[key] for key in row.keys()}
    data.setdefault("call_identity", data.get("identity"))
    data.setdefault("record_identity", data.get("source_identity"))
    data.setdefault("result_identity", data.get("identity"))
    data.setdefault("record_content", data.get("content"))
    data.setdefault("exported_at", data.get("exported_at"))
    data.setdefault("extracted_at", int(timestamp_now()))
    return data


def _write_ndjson(row: dict[str, Any], *, sink: TextIO) -> None:
    print(json.dumps(row, ensure_ascii=False, sort_keys=True), file=sink)


__all__ = [
    "mark_result_exported",
    "reset_result_exported",
    "write_extracted_result_record",
    "write_pending_result_records",
    "write_result_records_by_slugs",
]
