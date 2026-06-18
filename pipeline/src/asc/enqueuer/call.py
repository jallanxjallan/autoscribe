from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from asc.models.process.call import Call
from asc.redis.key import RedisKey


MANIFEST_FIELDS = {"record_type", "plan_slug"}
PROBATIONARY_CALL_TTL_SECONDS = 5 * 60
ENQUEUED_CALL_TTL_SECONDS = 60 * 60 * 24 * 30


def create_call_from_manifest_record(record: Mapping[str, Any]) -> Call:
    """Create and persist the ephemeral Call carried by one run manifest row.

    The enqueue stream row is a manifest. It is not a Call NDJSON record. Split
    off dispatch-only fields, build the Call from the document payload, and save
    it with a short probationary TTL. If the rest of enqueue succeeds, service
    promotes the Call TTL. If enqueue crashes midway, the orphaned Call expires.
    """

    call = Call(**_call_payload(record))
    call.save()
    expire_call(call, PROBATIONARY_CALL_TTL_SECONDS)
    return call


def promote_call_ttl(call: Call) -> None:
    expire_call(call, ENQUEUED_CALL_TTL_SECONDS)


def expire_call(call: Call, ttl_seconds: int) -> None:
    if ttl_seconds < 1:
        raise ValueError("ttl_seconds must be positive")
    RedisKey(str(call.redis_key)).expire(ttl_seconds)


def _call_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(record)
    for field in MANIFEST_FIELDS:
        payload.pop(field)

    source_identity = payload.pop("record_identity")
    content = payload.pop("record_content")

    return {
        "source_identity": source_identity,
        "content": content,
        **payload,
    }


def call_identity(call: Call) -> str:
    return str(call.identity)


def call_key(call: Call) -> str:
    return str(call.redis_key)


__all__ = [
    "ENQUEUED_CALL_TTL_SECONDS",
    "PROBATIONARY_CALL_TTL_SECONDS",
    "call_identity",
    "call_key",
    "create_call_from_manifest_record",
    "expire_call",
    "promote_call_ttl",
]
