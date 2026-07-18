import sys
from collections.abc import Iterable
from typing import TextIO

from asc.enqueue.job import activate_job, create_job, deactivate_job
from asc.enqueue.reader import EnqueueRecord, iter_enqueue_records
from asc.enqueue.report import EnqueuedCall, EnqueueReport
from asc.enqueue.runtime import materialize_runtimes


def enqueue_from_stream(stream: TextIO) -> EnqueueReport:
    try:
        records = tuple(iter_enqueue_records(stream))
        if not records:
            print("asc enqueue: no records sent in stream", file=sys.stderr)
            sys.exit(1)
        return enqueue_records(records)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"asc enqueue: record(s) failed validation: {exc}", file=sys.stderr)
        sys.exit(1)


def enqueue_records(records: Iterable[EnqueueRecord]) -> EnqueueReport:
    return EnqueueReport(records=tuple(enqueue_record(record) for record in records))


def enqueue_record(record: EnqueueRecord) -> EnqueuedCall:
    """Persist one call, compile its runtimes, and register its job."""

    call = record.call
    call_key = str(call.redis_key)
    runtimes = ()
    job = None
    job_activated = False

    try:
        call.save()
        runtimes = materialize_runtimes(
            call_identity=call.identity,
            plan=record.plan.plan,
        )
        job = create_job(
            call_identity=call.identity,
            plan_identity=str(record.plan.plan.identity),
            total_steps=record.plan.step_count,
        )
        activate_job(job)
        job_activated = True
    except Exception:
        if job is not None:
            if job_activated:
                deactivate_job(job)
            else:
                job.delete()
        for runtime in runtimes:
            runtime.delete()
        call.delete()
        raise

    return EnqueuedCall(
        call=call.redis_key.identity,
        source_identity=record.source_identity,
        call_key=call_key,
        runtime_keys=tuple(runtime.raw_key for runtime in runtimes),
        job_key=job.raw_key,
        plan_key=record.plan.plan_key,
        step_count=record.plan.step_count,
    )


__all__ = ["EnqueueReport", "EnqueuedCall", "enqueue_from_stream", "enqueue_record", "enqueue_records"]
