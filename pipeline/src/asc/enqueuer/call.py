from collections.abc import Mapping
from typing import Any

from asc.models.process.call import Call


MANIFEST_FIELDS = frozenset({"record_type", "plan_slug"})
PROBATIONARY_CALL_TTL_SECONDS = 5 * 60
ENQUEUED_CALL_TTL_SECONDS = 60 * 60 * 24 * 30


def create_call_from_manifest_record(
    record: Mapping[str, Any],
    *,
    plan_key: str,
) -> Call:
    """Create and persist the ephemeral Call carried by one run manifest row.

    The enqueue stream row is a dispatch manifest, not a stored Call record.
    Split off dispatch-only fields, build the Call from the document payload,
    and save it with a short probationary TTL. If the full enqueue succeeds,
    the service promotes the Call TTL. If enqueue fails midway, the orphaned
    Call expires quickly.

    The resolved plan key is stored on the Call so the orchestrator can open the
    Call, open the Plan, and initialize runtime state without enqueue-time cursor
    or results-index creation.
    """

    call = Call(**_call_payload(record, plan_key=plan_key))
    call.save()
    expire_call(call, PROBATIONARY_CALL_TTL_SECONDS)
    return call


def promote_call_ttl(call: Call) -> None:
    expire_call(call, ENQUEUED_CALL_TTL_SECONDS)


def expire_call(call: Call, ttl_seconds: int) -> None:
    if ttl_seconds < 1:
        raise ValueError("ttl_seconds must be positive")
    call.redis_key.expire(ttl_seconds)


def _call_payload(record: Mapping[str, Any], *, plan_key: str) -> dict[str, Any]:
    payload = dict(record)
    for field in MANIFEST_FIELDS:
        payload.pop(field, None)

    try:
        source_identity = payload.pop("record_identity")
        content = payload.pop("record_content")
    except KeyError as exc:
        raise ValueError(f"manifest record missing required field: {exc.args[0]}") from exc

    return {
        "source_identity": source_identity,
        "content": content,
        "plan_key": str(plan_key),
        **payload,
    }


__all__ = [
    "ENQUEUED_CALL_TTL_SECONDS",
    "PROBATIONARY_CALL_TTL_SECONDS",
    "create_call_from_manifest_record",
    "expire_call",
    "promote_call_ttl",
]
