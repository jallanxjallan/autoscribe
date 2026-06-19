from __future__ import annotations

from collections.abc import Iterable
from typing import TextIO

from asc.enqueuer.call import call_identity, call_key, promote_call_ttl
from asc.enqueuer.factories import build_runtime_cursor, save_runtime_cursor, build_response_index
from asc.enqueuer.queue import enqueue_cursor
from asc.enqueuer.reader import EnqueueRecord, iter_enqueue_records
from asc.enqueuer.report import EnqueuedCall, EnqueueReport


def enqueue_from_stream(stream: TextIO) -> EnqueueReport:
    return enqueue_records(iter_enqueue_records(stream))


def enqueue_records(records: Iterable[EnqueueRecord]) -> EnqueueReport:
    return EnqueueReport(records=tuple(enqueue_record(record) for record in records))


def enqueue_record(record: EnqueueRecord) -> EnqueuedCall:
    call = record.call
    plan = record.plan

    identity = call_identity(call)
    stored_call_key = call_key(call)

    build_response_index(
        identity=identity,
        call_key=stored_call_key,
        total_steps=plan.step_count,
    )

    cursor = build_runtime_cursor(
        identity=identity,
        call_key=stored_call_key,
        plan_key=plan.key,
    )
    cursor_key = save_runtime_cursor(cursor)
    enqueue_cursor(cursor_key)
    promote_call_ttl(call)

    return EnqueuedCall(
        call=identity,
        source_identity=record.source_identity,
        cursor_key=cursor_key,
        call_key=stored_call_key,
        plan_key=plan.key,
        step_count=plan.step_count,
    )


__all__ = [
    "EnqueueReport",
    "EnqueuedCall",
    "enqueue_cursor",
    "enqueue_from_stream",
    "enqueue_record",
    "enqueue_records",
]
