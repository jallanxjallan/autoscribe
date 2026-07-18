from collections.abc import Mapping
from typing import Any

from asc.models.process.call import CallRecord


ENQUEUE_CONTROL_FIELDS = frozenset({"record_type", "record_plan", "plan_slug"})


def create_call_from_manifest_record(
    record: Mapping[str, Any],
    *,
    plan_key: str,
) -> CallRecord:
    """Create and persist the CallRecord carried by one dispatch NDJSON row."""

    return CallRecord(**_call_payload(record, plan_key=plan_key))


def _call_payload(record: Mapping[str, Any], *, plan_key: str) -> dict[str, Any]:
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
        "plan_key": str(plan_key),
        **payload,
    }


__all__ = ["create_call_from_manifest_record"]
