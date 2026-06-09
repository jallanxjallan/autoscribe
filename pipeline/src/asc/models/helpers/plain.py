from __future__ import annotations

from typing import Any

REDIS_KEY_SEPARATOR = ":"


class PlainValueError(ValueError):
    """Raised when a model field does not resolve to the expected plain value."""


def plain_non_empty_string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise PlainValueError(f"{name} must be a plain string")
    value = value.strip()
    if not value:
        raise PlainValueError(f"{name} must be non-empty")
    return value


def optional_plain_string(value: object, name: str) -> str | None:
    if value is None:
        return None
    return plain_non_empty_string(value, name)


def redis_key_segment_text(value: object, name: str) -> str:
    value = plain_non_empty_string(value, name)
    if REDIS_KEY_SEPARATOR in value:
        raise PlainValueError(f"{name} must not contain '{REDIS_KEY_SEPARATOR}'")
    return value


def positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise PlainValueError(f"{name} must be an integer")
    if value < 1:
        raise PlainValueError(f"{name} must be greater than zero")
    return value


def string_list(value: object, name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise PlainValueError(f"{name} must be a list of strings")
    return [plain_non_empty_string(item, f"{name}[{index}]") for index, item in enumerate(value)]


# Kept as a compatibility name. It no longer enforces the old three-part slug
# contract; record_identity is now just a non-empty Redis-safe text identity.
def slug_like_text(value: object, name: str = "slug") -> str:
    return redis_key_segment_text(value, name)


def required_plain_string(values: dict[str, Any], key: str, *, label: str = "frontmatter") -> str:
    return plain_non_empty_string(values.get(key), f"{label}.{key}")


__all__ = [
    "PlainValueError",
    "optional_plain_string",
    "plain_non_empty_string",
    "positive_int",
    "redis_key_segment_text",
    "required_plain_string",
    "slug_like_text",
    "string_list",
]
