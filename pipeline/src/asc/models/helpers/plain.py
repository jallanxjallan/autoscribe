from __future__ import annotations

from typing import Any

REDIS_KEY_SEPARATOR = ":"


class PlainValueError(ValueError):
    """Raised when a model field does not resolve to the expected plain value."""


def required_plain_string(values: dict[str, Any], key: str, *, label: str = "frontmatter") -> str:
    """Return a required non-empty plain string from a parsed mapping."""

    value = values.get(key)
    return plain_non_empty_string(value, f"{label}.{key}")


def plain_non_empty_string(value: object, name: str) -> str:
    """Validate and normalize a required non-empty plain string."""

    if not isinstance(value, str):
        raise PlainValueError(f"{name} must be a plain string")

    value = value.strip()

    if not value:
        raise PlainValueError(f"{name} must be non-empty")

    return value


def redis_key_segment_text(value: object, name: str) -> str:
    """Validate text that will occupy one Redis key segment."""

    value = plain_non_empty_string(value, name)

    if REDIS_KEY_SEPARATOR in value:
        raise PlainValueError(f"{name} must not contain '{REDIS_KEY_SEPARATOR}'")

    return value


def slug_like_text(value: object, name: str = "slug") -> str:
    """Validate asc's three-part dot-separated slug-like identity strings."""

    value = redis_key_segment_text(value, name)
    parts = value.split(".")

    if len(parts) != 3 or any(not part for part in parts):
        raise PlainValueError(f"{name} must be a three-part dot-separated string")

    return value


def string_list(value: object, name: str) -> list[str]:
    """Validate a list of plain strings."""

    if value is None:
        return []

    if not isinstance(value, list):
        raise PlainValueError(f"{name} must be a list of strings")

    normalized: list[str] = []

    for index, item in enumerate(value):
        normalized.append(plain_non_empty_string(item, f"{name}[{index}]"))

    return normalized


__all__ = [
    "PlainValueError",
    "plain_non_empty_string",
    "redis_key_segment_text",
    "required_plain_string",
    "slug_like_text",
    "string_list",
]
