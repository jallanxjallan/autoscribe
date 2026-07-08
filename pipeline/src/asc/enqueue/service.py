from collections.abc import Iterable
from typing import TextIO

from asc.enqueue.reader import EnqueueRecord, iter_enqueue_records
from asc.enqueue.report import EnqueuedCall, EnqueueReport
from asc.enqueue.runtime import activate_call, create_call_index


def enqueue_from_stream(stream: TextIO) -> EnqueueReport:
    return enqueue_records(iter_enqueue_records(stream))


def enqueue_records(records: Iterable[EnqueueRecord]) -> EnqueueReport:
    return EnqueueReport(records=tuple(enqueue_record(record) for record in records))


def enqueue_record(record: EnqueueRecord) -> EnqueuedCall:
    call = record.call
    call_key = str(call.redis_key)
    call_index_key = create_call_index(
        call_identity=call.redis_key.identity,
        call_key=call_key,
        plan_index=record.plan.plan_index,
    )
    activate_call(call_key)

    return EnqueuedCall(
        call=call.redis_key.identity,
        source_identity=record.source_identity,
        call_key=call_key,
        call_index_key=call_index_key,
        plan_key=record.plan.plan_key,
        step_count=record.plan.step_count,
    )


__all__ = [
    "EnqueueReport",
    "EnqueuedCall",
    "enqueue_from_stream",
    "enqueue_record",
    "enqueue_records",
]
