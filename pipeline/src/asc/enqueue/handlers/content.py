from collections.abc import Mapping
from typing import Any

from asc.enqueue.reader import EnqueueRecord
from asc.enqueue.report import EnqueuedCall
from asc.enqueue.service import enqueue_record
from asc.enqueue.call import create_call_from_manifest_record
from asc.enqueue.directive import extract_leading_directive
from asc.enqueue.plan import load_plan_from_manifest_record


def enqueue_content(record: Mapping[str, Any]) -> EnqueuedCall:
    """Validate and enqueue one content manifest record."""

    plan = load_plan_from_manifest_record(record)
    prepared = dict(record)
    extracted = extract_leading_directive(str(prepared.get("record_content", "")))
    prepared["record_content"] = extracted.content
    call = create_call_from_manifest_record(prepared, plan_key=plan.plan_key)
    return enqueue_record(
        EnqueueRecord(
            record_type="content",
            call_kind="call",
            plan=plan,
            call=call,
            raw_record=record,
            directive=extracted.directive,
        )
    )


__all__ = ["enqueue_content"]
