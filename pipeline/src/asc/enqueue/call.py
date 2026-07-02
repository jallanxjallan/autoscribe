from collections.abc import Mapping
from typing import Any

from asc.enqueue.plan import LoadedPlan
from asc.models.process.call import CallRecord


ENQUEUE_CONTROL_FIELDS = frozenset({"record_type", "record_plan", "plan_slug"})


def create_call(record: Mapping[str, Any], *, plan: LoadedPlan) -> CallRecord:
    """Create and save the runtime call for one dispatch record."""

    call = CallRecord(**_call_payload(record, plan=plan))
    call.save()
    return call


def _call_payload(record: Mapping[str, Any], *, plan: LoadedPlan) -> dict[str, Any]:
    payload = dict(record)
    for field in ENQUEUE_CONTROL_FIELDS:
        payload.pop(field, None)

    try:
        source_identity = payload.pop("record_identity")
        content = payload.pop("record_content")
    except KeyError as exc:
        raise ValueError(f"enqueue record missing required field: {exc.args[0]}") from exc

    return {
        "source_identity": source_identity,
        "content": content,
        "plan_key": plan.raw_key,
        **payload,
    }


__all__ = ["create_call"]
