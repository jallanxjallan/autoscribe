import sys
from typing import TextIO

from asc.scrivener.connect import LedgerConnection
from asc.exporter._ledger import (
    DEFAULT_EXPORT_MESSAGE,
    extracted_result_row,
    extracted_result_row_by_slug,
    mark_exported,
    pending_export_rows,
    reset_exported,
)
from asc.exporter._ndjson import write_ndjson_record


def write_extracted_result_record(
    call_identity: str,
    *,
    conn: LedgerConnection,
    sink: TextIO = sys.stdout,
    export_message: str = DEFAULT_EXPORT_MESSAGE,
) -> int:
    """Write one extracted call/result row as NDJSON and mark it exported."""

    row = extracted_result_row(conn=conn, call_identity=call_identity)
    if row is None:
        raise ValueError(f"no extractable result row for call {call_identity}")

    record = _export_record(row=row, call_identity=call_identity)
    write_ndjson_record(record, sink)
    _flush(sink)
    mark_exported(
        conn=conn,
        result_identity=str(row.get("call_identity") or call_identity),
        export_message=export_message,
    )
    return 1


def write_pending_result_records(
    *,
    conn: LedgerConnection,
    sink: TextIO = sys.stdout,
    export_message: str = DEFAULT_EXPORT_MESSAGE,
) -> int:
    """Write every pending extracted call/result row as an NDJSON batch and mark them exported."""

    count = 0
    exported_call_identities: list[str] = []
    for pending in pending_export_rows(conn=conn):
        call_identity = str(pending["call_identity"])
        row = extracted_result_row(conn=conn, call_identity=call_identity)
        if row is None:
            raise ValueError(f"no extractable result row for call {call_identity}")
        write_ndjson_record(_export_record(row=row, call_identity=call_identity), sink)
        exported_call_identities.append(call_identity)
        count += 1

    _flush(sink)

    for call_identity in exported_call_identities:
        mark_exported(
            conn=conn,
            result_identity=call_identity,
            export_message=export_message,
        )

    return count



def write_result_record_by_slug(
    slug: str,
    *,
    conn: LedgerConnection,
    sink: TextIO = sys.stdout,
    export_message: str = DEFAULT_EXPORT_MESSAGE,
) -> int:
    """Write the most recent result row for a source slug as NDJSON and mark it exported."""

    row = extracted_result_row_by_slug(conn=conn, slug=slug)
    if row is None:
        raise ValueError(f"no extractable result row for slug {slug}")

    call_identity = str(row.get("call_identity") or "").strip()
    if not call_identity:
        raise ValueError(f"extractable result row for slug {slug} is missing call identity")

    write_ndjson_record(_export_record(row=row, call_identity=call_identity), sink)
    _flush(sink)
    mark_exported(
        conn=conn,
        result_identity=call_identity,
        export_message=export_message,
    )
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


def reset_result_exported(
    identities: list[str],
    *,
    conn: LedgerConnection,
    export_message: str = "reset",
) -> int:
    """Reset exported_at to zero for call/result/source identities."""

    return reset_exported(conn=conn, identities=identities, export_message=export_message)


def _export_record(*, row: dict[str, object], call_identity: str) -> dict[str, object]:
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

    slug = row.get("slug")
    if slug:
        record["record_slug"] = slug

    result_identity = row.get("result_identity")
    result_key = row.get("result_key")
    if result_identity is not None:
        record["result_identity"] = result_identity
    elif result_key is not None:
        record["result_identity"] = str(result_key).split(":", 1)[-1].split(":", 1)[0]

    return record


def _flush(sink: TextIO) -> None:
    try:
        sink.flush()
    except Exception:
        pass


__all__ = [
    "DEFAULT_EXPORT_MESSAGE",
    "mark_result_exported",
    "reset_result_exported",
    "write_extracted_result_record",
    "write_pending_result_records",
    "write_result_record_by_slug",
]
