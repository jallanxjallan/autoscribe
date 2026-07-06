from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from asc.redis.key import RedisKey
from asc.redis.primitives.hashes import hgetall


CONTENT_FIELDS = (
    "content",
    "record_content",
    "text",
    "body",
)


@dataclass(frozen=True, slots=True)
class RuntimeInput:
    """Concrete runtime input loaded from Redis for an engine call."""

    key: str
    content: str
    fields: Mapping[str, Any]


def load_runtime_input(key: str) -> RuntimeInput:
    """Load the worker input record without interpreting engine semantics."""
    if not isinstance(key, str) or not key.strip():
        raise ValueError("runtime input key must be non-empty")

    clean_key = key.strip()
    data = hgetall(RedisKey(clean_key))
    if not data:
        raise ValueError(f"runtime input key is missing or empty: {clean_key}")

    content = _content_from_fields(data)
    if content is None:
        raise ValueError(
            f"runtime input key has no content field: {clean_key} "
            f"available={sorted(str(name) for name in data)}"
        )

    return RuntimeInput(
        key=clean_key,
        content=content,
        fields=data,
    )


def load_runtime_content(key: str) -> str:
    """Backward-compatible helper for callers that only need the text body."""
    return load_runtime_input(key).content


def _content_from_fields(data: Mapping[str, Any]) -> str | None:
    for field in CONTENT_FIELDS:
        value = data.get(field)
        if value is not None:
            return str(value)

    raw_json = data.get("raw_json") or data.get("record_content_json") or data.get("raw_record_json")
    if raw_json:
        return _content_from_json(raw_json)

    return None


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


__all__ = ["RuntimeInput", "load_runtime_content", "load_runtime_input"]
