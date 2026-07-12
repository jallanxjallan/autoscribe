from collections.abc import Iterable

from asc.ingest.common import IngestReport, IngestedItem
from asc.ingest.record import ingest_record
from asc.ingest.record_types import canonical_target


def ingest_records(
    records: Iterable[object],
    *,
    target: str = "all",
) -> IngestReport:
    expected = canonical_target(target)
    saved: list[IngestedItem] = []
    by_type: dict[str, int] = {}

    for raw_record in records:
        item = ingest_record(raw_record, target=expected)
        saved.append(item)
        by_type[item.record_type] = by_type.get(item.record_type, 0) + 1

    return IngestReport(
        record_count=len(saved),
        by_type=by_type,
        records=tuple(saved),
    )


__all__ = ["ingest_records"]
