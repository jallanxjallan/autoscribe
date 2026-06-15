from __future__ import annotations

import sys
from typing import TextIO

from asc.scrivener.records.call import read_call_record_with_connection
from asc.scrivener.connect import LedgerConnection
from asc.scrivener.records.result import (
    read_pending_result_export_records_with_connection,
    require_unique_pending_export_slugs_with_connection,
)
from asc.streams import write_ndjson_record


def pending_export_records(
    *,
    conn: LedgerConnection,
    plan_slug: str | None = None,
) -> list[dict[str, object]]:
    """Return pending writeback rows owned by the ledger.

    The ledger query owns pending-export custody. This helper only applies the
    optional client-facing plan filter by reading call custody rows through the
    ledger call API.
    """

    require_unique_pending_export_slugs_with_connection(conn=conn)

    rows = [
        dict(row)
        for row in read_pending_result_export_records_with_connection(conn=conn)
    ]

    if plan_slug is None:
        return rows

    selected: list[dict[str, object]] = []
    for row in rows:
        call_identity = str(row["call_identity"])
        call = read_call_record_with_connection(
            conn=conn,
            call_identity=call_identity,
        )
        if call is not None and call.get("plan_slug") == plan_slug:
            selected.append(row)

    return selected


def write_pending_export_records(
    *,
    conn: LedgerConnection,
    sink: TextIO = sys.stdout,
    plan_slug: str | None = None,
) -> int:
    """Write the pending writeback worklist as NDJSON.

    Rows contain prompt_slug, call_identity, and result_identity. The optional
    plan_slug filter is a presentation/export concern; pending-result custody
    stays in asc.ledger.result_record.
    """

    count = 0
    for row in pending_export_records(conn=conn, plan_slug=plan_slug):
        write_ndjson_record(row, sink)
        count += 1

    _flush(sink)
    return count


def _flush(sink: TextIO) -> None:
    try:
        sink.flush()
    except Exception:
        pass


__all__ = ["pending_export_records", "write_pending_export_records"]
