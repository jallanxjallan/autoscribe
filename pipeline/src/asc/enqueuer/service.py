from __future__ import annotations

from collections.abc import Iterable
import sys
from typing import TextIO

from asc.enqueuer.call import load_non_empty_call
from asc.enqueuer.cursor_factory import build_runtime_cursor, save_runtime_cursor
from asc.enqueuer.keys import resolve_enqueue_keys
from asc.enqueuer.plan import load_runnable_plan_step_count
from asc.enqueuer.queue import enqueue_cursor
from asc.enqueuer.reader import EnqueueRecord, iter_enqueue_records
from asc.enqueuer.report import EnqueuedCall, EnqueueReport
from asc.enqueuer.response_index import create_response_index


def enqueue_from_stream(stream: TextIO) -> EnqueueReport:
    return enqueue_records(iter_enqueue_records(stream))


def enqueue_records(records: Iterable[EnqueueRecord]) -> EnqueueReport:
    enqueued: list[EnqueuedCall] = []

    for record_number, record in enumerate(records, start=1):
        try:
            enqueued.append(enqueue_record(record))
        except Exception as exc:
            identifier = _record_identifier(record, fallback=f"record {record_number}")
            print(
                f"[enqueue] {identifier}: skipped invalid run spec record: {exc}",
                file=sys.stderr,
            )

    return EnqueueReport(records=tuple(enqueued))


def enqueue_record(record: EnqueueRecord) -> EnqueuedCall:
    keys = resolve_enqueue_keys(record)

    load_non_empty_call(keys.call_key)
    step_count = load_runnable_plan_step_count(keys.plan_key)

    create_response_index(
        identity=keys.call_identity,
        call_key=keys.call_key,
        total_steps=step_count,
    )

    cursor = build_runtime_cursor(keys)
    cursor_key = save_runtime_cursor(cursor)
    enqueue_cursor(cursor_key)

    return EnqueuedCall(
        call=keys.call_identity,
        cursor_key=cursor_key,
        call_key=keys.call_key,
        plan_key=keys.plan_key,
        step_count=step_count,
    )


def _record_identifier(record: object, *, fallback: str) -> str:
    if isinstance(record, EnqueueRecord):
        return record.call_slug
    return fallback


__all__ = [
    "EnqueueReport",
    "EnqueuedCall",
    "enqueue_cursor",
    "enqueue_from_stream",
    "enqueue_record",
    "enqueue_records",
]
