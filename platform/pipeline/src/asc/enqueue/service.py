import sys
from collections.abc import Iterable
from typing import TextIO

from asc.control.repository import control_revision
from asc.enqueue.job import activate_job, create_job, deactivate_job
from asc.enqueue.plan import load_plan
from asc.enqueue.reader import EnqueueRecord, iter_enqueue_records
from asc.enqueue.report import EnqueuedCall, EnqueueReport
from asc.enqueue.runtime import delete_ephemeral_instructions, materialize_runtimes
from asc.models.process.result import record_failure


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
        failure_key = record_failure(stage="enqueue.stream", exc=exc)
        print(
            f"asc enqueue: record(s) failed validation: {exc} failure_key={failure_key}",
            file=sys.stderr,
        )
        sys.exit(1)


def enqueue_records(records: Iterable[EnqueueRecord]) -> EnqueueReport:
    return EnqueueReport(records=tuple(enqueue_record(record) for record in records))


def enqueue_record(record: EnqueueRecord) -> EnqueuedCall:
    """Persist one call, compile its runtimes, and register its job."""

    call = record.call
    call_key = record.call_key
    runtimes = ()
    job = None
    job_activated = False
    plan_key = record.plan_slug

    try:
        revision = control_revision()
        plan = load_plan(record.plan_slug, revision=revision)
        plan_key = plan.plan_key
        runtimes = materialize_runtimes(
            call_identity=call.identity,
            plan=plan.plan,
            control_revision=revision,
            directive=record.directive,
            instruction_sources=plan.instructions,
        )
        job = create_job(
            call_identity=call.identity,
            plan_identity=str(plan.plan.identity),
            total_steps=plan.step_count,
        )
        activate_job(job)
        job_activated = True
    except Exception as exc:
        if job is not None:
            if job_activated:
                deactivate_job(job)
            else:
                job.delete()
        delete_ephemeral_instructions(runtimes)
        for runtime in runtimes:
            runtime.delete()
        record_failure(
            stage="enqueue.record",
            exc=exc,
            process_identity=call.identity,
            source_identity=record.source_identity,
            call_key=call_key,
            plan_key=plan_key,
        )
        raise

    return EnqueuedCall(
        call=call.redis_key.identity,
        source_identity=record.source_identity,
        call_key=call_key,
        runtime_keys=tuple(runtime.raw_key for runtime in runtimes),
        job_key=job.raw_key,
        plan_key=plan_key,
        step_count=plan.step_count,
    )


__all__ = ["EnqueueReport", "EnqueuedCall", "enqueue_from_stream", "enqueue_record", "enqueue_records"]
