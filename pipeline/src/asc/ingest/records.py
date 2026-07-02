import sys
from collections.abc import Iterable
from typing import TextIO

from asc.ingest.common import IngestReport, IngestedItem, SkippedIngest
from asc.ingest.record import ingest_record, record_identifier
from asc.ingest.record_types import canonical_target


def ingest_records(
    records: Iterable[object],
    *,
    target: str = "all",
    error_stream: TextIO = sys.stderr,
) -> IngestReport:
    expected = canonical_target(target)
    saved: list[IngestedItem] = []
    skipped: list[SkippedIngest] = []
    by_type: dict[str, int] = {}

    for record_number, raw_record in enumerate(records, start=1):
        location = f"record {record_number}"
        try:
            item = ingest_record(raw_record, target=expected)
        except Exception as exc:
            identifier = record_identifier(raw_record, fallback=location)
            skipped.append(SkippedIngest(record_type=expected, location=location, identifier=identifier, error=str(exc)))
            print(f"[ingest:{expected}] skipping {location} ({identifier}): {exc}", file=error_stream)
            continue

        saved.append(item)
        by_type[item.record_type] = by_type.get(item.record_type, 0) + 1

    return IngestReport(
        record_count=len(saved),
        skipped_count=len(skipped),
        by_type=by_type,
        records=tuple(saved),
        skipped=tuple(skipped),
    )


__all__ = ["ingest_records"]
