from __future__ import annotations

from typing import Any

from asc.models.helpers.plain import plain_non_empty_string, string_list


JsonObject = dict[str, Any]


def plain_object(value: object, field_name: str) -> JsonObject:
    """Validate a plain JSON object with non-empty string keys."""
    if value is None:
        return {}

    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")

    cleaned: JsonObject = {}

    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{field_name} keys must be non-empty strings")

        cleaned[key.strip()] = item

    return cleaned


def optional_text(value: object, field_name: str) -> str:
    """Validate optional plain text fields used by uploaded controls."""
    if value is None:
        return ""

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a plain string")

    return value


def required_text(value: object, field_name: str) -> str:
    """Validate mandatory uploaded text fields."""
    return plain_non_empty_string(value, field_name)


def asset_list(value: object) -> list[str]:
    """Validate the shared uploaded-control assets field."""
    return string_list(value, "assets")

def populate_identity_from_identifier(value: object) -> object:
    if not isinstance(value, dict):
        return value

    data = dict(value)
    identity = data.get("identity") or data.get("identifier") or data.get("slug")
    data["identity"] = plain_non_empty_string(identity, "identity")

    if not data.get("identifier"):
        data["identifier"] = data["identity"]

    return data


__all__ = [
    "JsonObject",
    "asset_list",
    "optional_text",
    "plain_object",
    "required_text",
    "populate_identity_from_identifier"
]
