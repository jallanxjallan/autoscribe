from __future__ import annotations

from collections.abc import Iterable
from typing import TextIO

from asc.enqueuer.call import call_identity, call_key, promote_call_ttl
from asc.enqueuer.reader import EnqueueRecord, iter_enqueue_records
from asc.enqueuer.report import EnqueuedCall, EnqueueReport
from asc.enqueuer.results import create_results_index
from asc.enqueuer.cursor import insert_runtime_cursor


def enqueue_from_stream(stream: TextIO) -> EnqueueReport:
    return enqueue_records(iter_enqueue_records(stream))


def enqueue_records(records: Iterable[EnqueueRecord]) -> EnqueueReport:
    return EnqueueReport(records=tuple(enqueue_record(record) for record in records))


def enqueue_record(record: EnqueueRecord) -> EnqueuedCall:
    call = record.call
    plan = record.plan

    identity = call_identity(call)
    stored_call_key = call_key(call)

    results_key = create_results_index(
        identity=identity,
        call_identity=identity,
        total_steps=plan.step_count,
    )

    cursor_key = insert_runtime_cursor(
        identity=identity,
        call_key=stored_call_key,
        plan_key=plan.key,
    )
    promote_call_ttl(call)

    return EnqueuedCall(
        call=identity,
        source_identity=record.source_identity,
        cursor_key=cursor_key,
        call_key=stored_call_key,
        plan_key=plan.key,
        results_index_key=str(results_key),
        cursor_index_key=str(cursor_key),
        step_count=plan.step_count,
    )


__all__ = [
    "EnqueueReport",
    "EnqueuedCall",
    "enqueue_from_stream",
    "enqueue_record",
    "enqueue_records",
]
