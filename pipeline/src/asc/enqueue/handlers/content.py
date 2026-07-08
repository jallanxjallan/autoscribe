from collections.abc import Mapping
from typing import Any

from asc.enqueue.call import create_call
from asc.enqueue.plan import load_plan_for_record
from asc.enqueue.report import EnqueuedCall
from asc.enqueue.runtime import activate_call, create_call_index


def enqueue_content(record: Mapping[str, Any]) -> EnqueuedCall:
    plan = load_plan_for_record(record)
    call = create_call(record, plan=plan)
    call_index_key = create_call_index(call=call, plan=plan)
    activate_call(call)

    return EnqueuedCall(
        call=call.redis_key.identity,
        source_identity=str(call.source_identity),
        call_key=call.redis_key.raw_key,
        call_index_key=call_index_key.raw_key,
        plan_key=plan.raw_key,
        step_count=plan.step_count,
    )


__all__ = ["enqueue_content"]
