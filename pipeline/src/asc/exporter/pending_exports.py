import sys
from typing import TextIO

from asc.scrivener.connect import LedgerConnection
from asc.exporter._ledger import pending_export_rows
from asc.exporter._ndjson import write_ndjson_record


def pending_export_records(
    *,
    conn: LedgerConnection,
    plan_slug: str | None = None,
    source_identity: str | None = None,
) -> list[dict[str, object]]:
    """Return pending writeback rows owned by the ledger.

    ``plan_slug`` is retained as a compatibility shim for the current CLI.  In
    the split ledger schema, this filter maps to ``source_identity``.
    """

    selected_source_identity = source_identity if source_identity is not None else plan_slug
    return pending_export_rows(conn=conn, source_identity=selected_source_identity)


def write_pending_export_records(
    *,
    conn: LedgerConnection,
    sink: TextIO = sys.stdout,
    plan_slug: str | None = None,
    source_identity: str | None = None,
) -> int:
    """Write the pending writeback worklist as NDJSON."""

    count = 0
    for row in pending_export_records(
        conn=conn,
        plan_slug=plan_slug,
        source_identity=source_identity,
    ):
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
