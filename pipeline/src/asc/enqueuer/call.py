from __future__ import annotations

from asc.models.process.call import Call


def load_non_empty_call(call_key: str) -> Call:
    """Load a call and require its canonical content field to be non-empty."""

    call = Call.load(call_key)
    content = getattr(call, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise ValueError(f"call has empty content: {call_key}")
    return call


__all__ = ["load_non_empty_call"]
