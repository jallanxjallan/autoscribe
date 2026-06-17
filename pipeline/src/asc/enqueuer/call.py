from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from asc.models.runtime.call import Call


def load_non_empty_call(call_key: str) -> Call:
    """Load a call and fail early if it has no usable content."""
    call = Call.load(call_key)
    content = call_content(call)
    if not isinstance(content, str) or not content.strip():
        raise ValueError(f"call has empty content: {call_key}")
    return call


def call_content(call: Any) -> str:
    for name in ("record_content", "content", "prompt", "text"):
        value = getattr(call, name, None)
        text = _text_from_value(value)
        if text.strip():
            return text

    raw_record = getattr(call, "raw_record", None)
    if isinstance(raw_record, Mapping):
        for name in ("record_content", "content", "prompt", "text"):
            text = _text_from_value(raw_record.get(name))
            if text.strip():
                return text

    return ""


def _text_from_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        for key in ("content", "text", "markdown", "body"):
            nested = value.get(key)
            if isinstance(nested, str) and nested.strip():
                return nested
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        parts = [item for item in value if isinstance(item, str) and item.strip()]
        return "\n".join(parts)
    return ""


__all__ = ["call_content", "load_non_empty_call"]
