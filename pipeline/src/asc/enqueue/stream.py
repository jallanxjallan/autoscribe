from collections.abc import Iterator, Mapping
from typing import Any, TextIO

from asc.enqueue.records import enqueue_records
from asc.enqueue.report import EnqueueReport
from asc.streams.ndjson import iter_ndjson_records


def iter_enqueue_stream(stream: TextIO) -> Iterator[Mapping[str, Any]]:
    seen = False
    for parsed in iter_ndjson_records(stream):
        seen = True
        record = parsed.record
        if not isinstance(record, Mapping):
            raise ValueError(f"enqueue stream row {parsed.line_number} must be a JSON object")
        yield record

    if not seen:
        raise ValueError("no enqueue records found")


def enqueue_stream(stream: TextIO) -> EnqueueReport:
    return enqueue_records(iter_enqueue_stream(stream))


__all__ = ["enqueue_stream", "iter_enqueue_stream"]
