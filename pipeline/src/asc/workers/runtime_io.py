from __future__ import annotations

import json
from typing import Any

from asc.runtime.response_index import redis_client


CONTENT_FIELDS = (
    "content",
    "record_content",
    "text",
    "body",
)


def load_runtime_content(key: str) -> str:
    """Load text content from a call/result Redis hash.

    The response index deliberately stores only keys. Workers should not care
    whether the key points to the original CallRecord or a prior StepResult; both
    are runtime input records that must expose content.
    """
    if not isinstance(key, str) or not key.strip():
        raise ValueError("runtime input key must be non-empty")

    data = redis_client().hgetall(key.strip())
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
