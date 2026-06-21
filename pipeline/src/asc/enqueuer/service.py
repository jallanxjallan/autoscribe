from collections.abc import Iterable
from typing import TextIO

from asc.enqueuer.call import promote_call_ttl
from asc.enqueuer.cursor import insert_runtime_cursor
from asc.enqueuer.reader import EnqueueRecord, iter_enqueue_records
from asc.enqueuer.report import EnqueuedCall, EnqueueReport
from asc.enqueuer.results import create_results_index


def enqueue_from_stream(stream: TextIO) -> EnqueueReport:
    return enqueue_records(iter_enqueue_records(stream))


def enqueue_records(records: Iterable[EnqueueRecord]) -> EnqueueReport:
    return EnqueueReport(records=tuple(enqueue_record(record) for record in records))


def enqueue_record(record: EnqueueRecord) -> EnqueuedCall:
    results_key = create_results_index(
        call_key=record.call.redis_key,
        total_steps=record.plan.step_count,
    )

    cursor_key = insert_runtime_cursor(
        call_key=record.call.redis_key,
        plan_key=record.plan.key,
    )
    promote_call_ttl(record.call)

    return EnqueuedCall(
        call=record.call.redis_key.identity,
        source_identity=record.source_identity,
        cursor_key=cursor_key,
        call_key=str(record.call.redis_key),
        plan_key=record.plan.key,
        results_index_key=str(results_key),
        cursor_index_key=str(cursor_key),
        step_count=record.plan.step_count,
    )


__all__ = [
    "EnqueueReport",
    "EnqueuedCall",
    "enqueue_from_stream",
    "enqueue_record",
    "enqueue_records",
]
