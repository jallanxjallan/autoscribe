"""Short-lived in-process step markers.

The response index should show that the orchestrator has assigned a step before
that step produces a result or failure.  The index slot stores the marker key;
the marker itself stores the worker task key and a timestamp for watchdogs.
"""

from __future__ import annotations

import time
from typing import Any, Mapping

from asc.redis.key import RedisKey
from asc.state.redis import redis_client

from .common import cursor_key_for, required_text, task_key_for

DEFAULT_IN_PROCESS_TTL_SECONDS = 60 * 60


def in_process_key(identity: str, step_number: int) -> str:
    if int(step_number) < 1:
        raise ValueError(f"invalid in-process step number: {step_number}")
    return str(
        RedisKey.from_parts(
            "in_process",
            required_text(identity, "identity"),
            f"step.{int(step_number)}",
        )
    )


def make_in_process_marker(
    *,
    cursor: Any,
    worker_task: Any,
    ttl_seconds: int = DEFAULT_IN_PROCESS_TTL_SECONDS,
) -> str:
    """Persist an in-process marker and return its Redis key.

    The marker is intentionally a tiny Redis hash rather than another durable
    process model.  It is watchdog state, not process output.
    """

    identity = required_text(getattr(cursor, "identity", None), "cursor.identity")
    step_number = int(getattr(worker_task, "step_number", getattr(worker_task, "task_number", 0)))
    task_key = task_key_for(worker_task)
    marker_key = in_process_key(identity, step_number)

    created_at = int(time.time_ns())
    mapping: Mapping[str, str] = {
        "kind": "in_process",
        "identity": identity,
        "step_number": str(step_number),
        "task_key": task_key,
        "cursor_key": cursor_key_for(cursor),
        "created_at": str(created_at),
    }

    client = redis_client()
    client.hset(marker_key, mapping=mapping)
    client.expire(marker_key, int(ttl_seconds))
    return marker_key


def load_in_process_marker(marker_key: str) -> dict[str, str]:
    key = required_text(marker_key, "marker_key")
    if RedisKey(key).kind != "in_process":
        raise ValueError(f"expected in_process key, got: {key}")
    data = redis_client().hgetall(key)
    if not data:
        raise ValueError(f"missing in-process marker: {key}")
    return {str(k): str(v) for k, v in data.items()}


__all__ = [
    "DEFAULT_IN_PROCESS_TTL_SECONDS",
    "in_process_key",
    "load_in_process_marker",
    "make_in_process_marker",
]
