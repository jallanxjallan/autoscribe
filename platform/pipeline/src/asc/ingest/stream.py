from collections.abc import Iterable

from asc.ingest.common import IngestInputError, IngestReport
from asc.ingest.records import ingest_records
from asc.streams.ndjson import iter_ndjson_records


def ingest_stream(
    source: Iterable[str],
    *,
    target: str = "all",
) -> IngestReport:
    try:
        records = tuple(parsed.record for parsed in iter_ndjson_records(source))
    except (TypeError, ValueError) as exc:
        raise IngestInputError(f"record(s) failed validation: {exc}") from exc

    if not records:
        raise IngestInputError("no records sent in stream")

    return ingest_records(records, target=target)


__all__ = ["ingest_stream"]
