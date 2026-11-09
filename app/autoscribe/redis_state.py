from __future__ import annotations

import json
from dataclasses import dataclass

from biznet_common import redis

FORENSIC_TTL = 30 * 24 * 60 * 60
EXECUTOR_QUEUE_KEY = "queue:executor"
WORKER_QUEUE_KEY = "queue:worker"


@dataclass(frozen=True)
class MaterializedCall:
    call_id: str
    content_key: str
    baggage_key: str


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def store_json(client: redis.RedisClient, key: str, value: dict, ttl: int = FORENSIC_TTL) -> str:
    client.hset(key, {"json": _json(value)})
    client.expire(key, ttl)
    return key


def load_json(client: redis.RedisClient, key: str) -> dict:
    record = client.hgetall(key)
    if not record:
        raise redis.RedisError(f"missing Redis hash: {key}")
    raw = record.get("json")
    if raw is None:
        raise redis.RedisError(f"Redis hash does not contain json: {key}")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise redis.RedisError(f"invalid JSON in Redis hash: {key}") from exc
    if not isinstance(value, dict):
        raise redis.RedisError(f"Redis JSON value must be an object: {key}")
    return value


def materialize_call(client: redis.RedisClient, call_id: str, content: dict, baggage: dict) -> MaterializedCall:
    client.ping()
    content_key = f"call:{call_id}:content"
    baggage_key = f"call:{call_id}:baggage"
    store_json(client, content_key, content)
    store_json(client, baggage_key, baggage)
    return MaterializedCall(call_id=call_id, content_key=content_key, baggage_key=baggage_key)


def enqueue_call(client: redis.RedisClient, call_id: str) -> None:
    # Queue membership is the execution fact; there is no mutable call state flag.
    client.zadd(EXECUTOR_QUEUE_KEY, 0, call_id)
