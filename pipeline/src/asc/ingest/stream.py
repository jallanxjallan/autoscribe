import sys
from collections.abc import Iterable

from asc.ingest.common import IngestReport
from asc.ingest.records import ingest_records
from asc.streams.ndjson import iter_ndjson_records


def ingest_stream(
    source: Iterable[str],
    *,
    target: str = "all",
) -> IngestReport:
    try:
        records = tuple(parsed.record for parsed in iter_ndjson_records(source))
        if not records:
            print("asc upload: no records sent in stream", file=sys.stderr)
            sys.exit(1)
        return ingest_records(records, target=target)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"asc upload: record(s) failed validation: {exc}", file=sys.stderr)
        sys.exit(1)


__all__ = ["ingest_stream"]
