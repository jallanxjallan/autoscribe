from collections.abc import Mapping
from typing import Any

from asc.enqueue.call import create_call_from_manifest_record
from asc.enqueue.plan import load_plan_from_manifest_record
from asc.enqueue.report import EnqueuedCall
from asc.enqueue.runtime import activate_call, materialize_runtimes


def enqueue_content(record: Mapping[str, Any]) -> EnqueuedCall:
    """Compatibility entry point using the current record/runtime contract."""

    plan = load_plan_from_manifest_record(record)
    call = create_call_from_manifest_record(record, plan_key=plan.plan_key)
    call_key = call.raw_key

    try:
        call.save()
        runtimes = materialize_runtimes(call_identity=call.identity, plan=plan.plan)
        runtime_keys = tuple(runtime.raw_key for runtime in runtimes)
        activate_call(call_key)
    except Exception:
        call.delete()
        raise

    return EnqueuedCall(
        call=call.identity,
        source_identity=str(call.source_identity),
        call_key=call_key,
        runtime_keys=runtime_keys,
        plan_key=plan.plan_key,
        step_count=plan.step_count,
    )


__all__ = ["enqueue_content"]
