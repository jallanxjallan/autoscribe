import sys
from typing import TextIO

from asc.scrivener.connect import LedgerConnection
from asc.exporter._ledger import (
    DEFAULT_EXPORT_MESSAGE,
    extracted_result_row,
    mark_exported,
)
from asc.exporter._ndjson import write_ndjson_record


def write_extracted_result_record(
    call_identity: str,
    *,
    conn: LedgerConnection,
    sink: TextIO = sys.stdout,
) -> int:
    """Write one extracted call/result row as NDJSON."""

    row = extracted_result_row(conn=conn, call_identity=call_identity)
    if row is None:
        raise ValueError(f"no extractable result row for call {call_identity}")

    content = row.get("content")
    if content is None:
        raise ValueError(f"extractable result row for call {call_identity} is missing content")

    record_identity = row.get("record_identity") or row.get("source_identity")
    if record_identity is None:
        raise ValueError(
            f"extractable result row for call {call_identity} is missing record identity"
        )

    record: dict[str, object] = {
        "record_identity": record_identity,
        "record_content": content,
    }

    result_identity = row.get("result_identity")
    result_key = row.get("result_key")
    if result_identity is not None:
        record["result_identity"] = result_identity
    elif result_key is not None:
        record["result_identity"] = str(result_key).split(":", 1)[-1].split(":", 1)[0]

    write_ndjson_record(record, sink)
    _flush(sink)
    return 1


def mark_result_exported(
    result_identity: str,
    *,
    conn: LedgerConnection,
    export_message: str = DEFAULT_EXPORT_MESSAGE,
) -> int:
    """Mark one successfully written result as exported."""

    return mark_exported(
        conn=conn,
        result_identity=result_identity,
        export_message=export_message,
    )


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
