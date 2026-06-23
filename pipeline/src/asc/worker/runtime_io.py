import json
from typing import Any

from asc.redis.key import RedisKey
from asc.redis.primitives.hashes import hgetall


CONTENT_FIELDS = (
    "content",
    "record_content",
    "text",
    "body",
)


def load_runtime_content(key: str) -> str:
    """Load text content from a runtime Redis hash.

    Workers receive concrete input keys from their jobs. They should not know
    whether the input points at the original call record or a previous step
    result; both records only need to expose a content-like field.
    """
    if not isinstance(key, str) or not key.strip():
        raise ValueError("runtime input key must be non-empty")

    data = hgetall(RedisKey(key.strip()))
    if not data:
        raise ValueError(f"runtime input key is missing or empty: {key}")

    for field in CONTENT_FIELDS:
        value = data.get(field)
        if value is not None:
            return str(value)

    raw_json = data.get("raw_json") or data.get("record_content_json") or data.get("raw_record_json")
    if raw_json:
        extracted = _content_from_json(raw_json)
        if extracted is not None:
            return extracted

    raise ValueError(
        f"runtime input key has no content field: {key} "
        f"available={sorted(str(name) for name in data)}"
    )


def _content_from_json(raw_json: Any) -> str | None:
    try:
        payload = json.loads(str(raw_json))
    except (TypeError, ValueError):
        return None

    if isinstance(payload, dict):
        for field in CONTENT_FIELDS:
            value = payload.get(field)
            if value is not None:
                return str(value)
    return None


__all__ = ["load_runtime_content"]
