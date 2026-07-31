"""Export terminal result records from the reduced ledger."""

from __future__ import annotations

import json
from typing import Any, TextIO

from asc.ledger.connect import LedgerConnection
from asc.ledger.queries import SELECT_EXTRACT_RESULT_BY_CALL_IDENTITY_SQL
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
        e.created_at AS export_created_at,
        e.exported_at AS exported_at,
        e.export_message AS export_message
    FROM calls AS c
    JOIN results AS r
        ON r.identity = c.identity
    LEFT JOIN exports AS e
        ON e.result_identity = r.identity
    WHERE c.source_identity = ?
      AND r.status = 'success'
    ORDER BY r.created_at DESC, e.exported_at DESC, e.export_id DESC
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
    export_message: str = "writeback",
) -> None:
    """Emit selected pending results and create export receipts as one batch.

    Every supplied slug must resolve to exactly one currently pending successful
    result. Validation is completed before any NDJSON is emitted or export
    receipt is inserted.
    """

    ensure_ledger_schema(conn)
    cleaned = [slug.strip() for slug in slugs if slug.strip()]
    if not cleaned:
        raise ValueError("at least one slug is required")
    if len(cleaned) != len(set(cleaned)):
        raise ValueError("duplicate slugs are not allowed")

    pending_rows = read_pending_result_export_records_with_connection(conn=conn)
    by_slug: dict[str, list[dict[str, Any]]] = {}
    for pending in pending_rows:
        slug = str(pending.get("source_identity") or pending.get("record_identity") or "").strip()
        if slug:
            by_slug.setdefault(slug, []).append(pending)

    selected: list[dict[str, Any]] = []
    for slug in cleaned:
        matches = by_slug.get(slug, [])
        if not matches:
            raise ValueError(f"no pending result found for source slug: {slug}")
        if len(matches) != 1:
            raise ValueError(f"multiple pending results found for source slug: {slug}")

        extracted = read_extract_result_record_by_call_identity_with_connection(
            conn=conn,
            call_identity=str(matches[0]["call_identity"]),
        )
        if extracted is None:
            raise ValueError(f"terminal result disappeared for source slug: {slug}")
        selected.append(extracted)

    try:
        for row in selected:
            insert_export_record_with_connection(
                conn=conn,
                result_identity=str(row["identity"]),
                export_message=export_message,
                export_mode="writeback",
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    for row in selected:
        _write_ndjson(row, sink=sink)


def write_result_record_by_slug(
    *,
    slug: str,
    conn: LedgerConnection,
    sink: TextIO,
    export_message: str = "re-export",
) -> None:
    """Emit the latest successful result for a source identity and receipt it.

    This command is intentionally overwrite-oriented. Unlike normal pending
    export extraction, it can re-emit an already exported result.
    """

    ensure_ledger_schema(conn)
    cleaned = slug.strip()
    if not cleaned:
        raise ValueError("slug must not be empty")

    row = conn.execute(SELECT_LATEST_RESULT_BY_SOURCE_IDENTITY_SQL, (cleaned,)).fetchone()
    if row is None:
        raise ValueError(f"no successful result found for source identity: {cleaned}")

    data = _normalize_extract_row(row)
    _write_ndjson(data, sink=sink)
    insert_export_record_with_connection(
        conn=conn,
        result_identity=str(data["identity"]),
        export_message=export_message,
        export_mode="re-export",
    )


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
    "write_result_record_by_slug",
    "write_result_records_by_slugs",
]
