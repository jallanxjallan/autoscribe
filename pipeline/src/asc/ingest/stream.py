import sys
from collections.abc import Iterable
from typing import TextIO

from asc.streams.ndjson import NdjsonParseError, iter_ndjson_records
from asc.ingest.common import IngestReport
from asc.ingest.records import ingest_records


def ingest_stream(
    source: Iterable[str],
    *,
    target: str = "all",
    error_stream: TextIO = sys.stderr,
) -> IngestReport:
    try:
        records = (parsed.record for parsed in iter_ndjson_records(source))
        return ingest_records(records, target=target, error_stream=error_stream)
    except NdjsonParseError as exc:
        raise ValueError(str(exc)) from exc


__all__ = ["ingest_stream"]
