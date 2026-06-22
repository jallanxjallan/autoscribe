from collections.abc import Iterable
from typing import TextIO

from asc.enqueuer.call import promote_call_ttl
from asc.enqueuer.reader import EnqueueRecord, iter_enqueue_records
from asc.enqueuer.report import EnqueuedCall, EnqueueReport
from asc.orchestrator.inbox import post as post_to_orchestrator


def enqueue_from_stream(stream: TextIO) -> EnqueueReport:
    return enqueue_records(iter_enqueue_records(stream))


def enqueue_records(records: Iterable[EnqueueRecord]) -> EnqueueReport:
    return EnqueueReport(records=tuple(enqueue_record(record) for record in records))


def enqueue_record(record: EnqueueRecord) -> EnqueuedCall:
    call = record.call
    plan = record.plan.plan

    post_to_orchestrator(str(call.redis_key))
    promote_call_ttl(call)

    return EnqueuedCall(
        call=call.redis_key.identity,
        source_identity=record.source_identity,
        call_key=str(call.redis_key),
        plan_key=str(plan.redis_key),
        step_count=record.plan.step_count,
    )


__all__ = [
    "EnqueueReport",
    "EnqueuedCall",
    "enqueue_from_stream",
    "enqueue_record",
    "enqueue_records",
]
