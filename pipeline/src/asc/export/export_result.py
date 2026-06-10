from __future__ import annotations

import sys
from typing import TextIO

from asc.ledger.connect import LedgerConnection
from asc.ledger.records.export import insert_export_record_with_connection
from asc.ledger.records.result import read_extract_result_record_by_call_identity_with_connection
from asc.streams import write_ndjson_record


DEFAULT_EXPORT_MESSAGE = "writeback"


def write_extracted_result_record(
    call_identity: str,
    *,
    conn: LedgerConnection,
    sink: TextIO = sys.stdout,
) -> int:
    """Write one extracted call/result row as NDJSON.

    Lookup is by call identity because the writeback worklist uses
    call_identity as the stable selector. The returned row shape belongs to the
    ledger extraction query.
    """

    row = read_extract_result_record_by_call_identity_with_connection(
        conn=conn,
        call_identity=call_identity,
    )
    if row is None:
        raise ValueError(f"no extractable result row for call {call_identity}")

    content = row.get("content")
    if content is None:
        raise ValueError(f"extractable result row for call {call_identity} is missing content")

    write_ndjson_record(row, sink)
    _flush(sink)
    return 1


def mark_result_exported(
    result_identity: str,
    *,
    conn: LedgerConnection,
    export_message: str = DEFAULT_EXPORT_MESSAGE,
) -> int:
    """Insert the export custody row for one successfully written result."""

    insert_export_record_with_connection(
        conn=conn,
        result_identity=result_identity,
        export_message=export_message,
    )
    return 1


def _flush(sink: TextIO) -> None:
    try:
        sink.flush()
    except Exception:
        pass


__all__ = [
    "DEFAULT_EXPORT_MESSAGE",
    "mark_result_exported",
    "write_extracted_result_record",
]
