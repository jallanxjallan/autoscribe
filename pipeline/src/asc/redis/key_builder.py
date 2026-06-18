from __future__ import annotations


SEP = ":"
MIN_PARTS = 2


def build_key(*parts: str) -> str:
    """
    Build an AutoScribe Redis key.

    Redis keys must be shaped as:

        kind:identity[:suffix...]

    The first segment is the canonical model/control kind. The second segment
    is the shared identity. Any remaining segments are suffix/detail segments
    owned by the caller.
    """
    if len(parts) < MIN_PARTS:
        raise ValueError("Redis keys must have at least kind and identity segments")

    normalized: list[str] = []
    for index, value in enumerate(parts, start=1):
        if not isinstance(value, str):
            raise TypeError(f"key segment {index} must be a str")
        value = value.strip()
        if not value:
            raise ValueError(f"key segment {index} must be non-empty")
        if SEP in value:
            raise ValueError(f"key segment {index} must not contain '{SEP}'")
        normalized.append(value)

    return SEP.join(normalized)


__all__ = ["build_key", "SEP", "MIN_PARTS"]
