from collections.abc import Iterable, Mapping
from typing import Any

from asc.enqueue.record import enqueue_record
from asc.enqueue.report import EnqueueReport


def enqueue_records(records: Iterable[Mapping[str, Any]]) -> EnqueueReport:
    return EnqueueReport(records=tuple(enqueue_record(record) for record in records))


__all__ = ["enqueue_records"]
