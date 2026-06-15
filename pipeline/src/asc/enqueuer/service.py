from __future__ import annotations

from collections.abc import Iterable
import sys
from typing import TextIO

from asc.enqueuer.call import load_non_empty_call
from asc.enqueuer.cursor_factory import build_runtime_cursor, save_runtime_cursor
from asc.enqueuer.keys import resolve_enqueue_keys
from asc.enqueuer.normalize import enqueue_record_identifier, normalize_enqueue_record
from asc.enqueuer.plan_steps import load_plan_steps
from asc.enqueuer.queue import enqueue_cursor
from asc.enqueuer.reader import iter_enqueue_records
from asc.enqueuer.report import EnqueuedCall, EnqueueReport


def enqueue_from_stream(stream: TextIO) -> EnqueueReport:
    return enqueue_records(iter_enqueue_records(stream))


def enqueue_records(records: Iterable[object]) -> EnqueueReport:
    enqueued: list[EnqueuedCall] = []

    for record_number, record in enumerate(records, start=1):
        try:
            enqueued.append(enqueue_record(record))
        except Exception as exc:
            identifier = enqueue_record_identifier(record, fallback=f"record {record_number}")
            print(
                f"[enqueue] {identifier}: skipped invalid run spec record: {exc}",
                file=sys.stderr,
            )

    return EnqueueReport(records=tuple(enqueued))


def enqueue_record(record: object) -> EnqueuedCall:
    dispatch = normalize_enqueue_record(record)
    keys = resolve_enqueue_keys(dispatch)

    load_non_empty_call(keys.call_key)
    plan_steps = load_plan_steps(keys.plan_key)

    cursor = build_runtime_cursor(keys, plan_steps=plan_steps)
    cursor_key = save_runtime_cursor(cursor)
    enqueue_cursor(cursor_key)

    return EnqueuedCall(
        call=keys.call_identity,
        cursor_key=cursor_key,
        call_key=keys.call_key,
        plan_key=keys.plan_key,
        response_index_key=str(getattr(cursor, "response_index_key", "")),
        step_count=len(plan_steps),
    )


__all__ = [
    "EnqueueReport",
    "EnqueuedCall",
    "enqueue_cursor",
    "enqueue_from_stream",
    "enqueue_record",
    "enqueue_records",
]
