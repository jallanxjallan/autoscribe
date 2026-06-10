from __future__ import annotations

import json
from typing import Any

from pydantic import BeforeValidator, PlainSerializer
from typing_extensions import Annotated

from asc.models.helpers.plain import PlainValueError, plain_non_empty_string, redis_key_segment_text

JsonObject = dict[str, Any]


def plain_object(value: object, field_name: str) -> JsonObject:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    return dict(value)


def optional_text(value: object, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a plain string")
    return value


def required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty plain string")
    return value.strip()


def record_type_text(value: object, *, expected: str) -> str:
    if not isinstance(value, str):
        raise ValueError("record_type must be a plain string")
    value = value.strip()
    if value != expected:
        raise ValueError(f"record_type must be {expected!r}")
    return value


def record_identity_text(value: object) -> str:
    text = redis_key_segment_text(value, "record_identity")
    if len(text) < 6:
        raise PlainValueError("record_identity must be at least 6 characters")
    if not any(separator in text for separator in (".", "-", "_")):
        raise PlainValueError("record_identity must contain a separator such as '.', '-', or '_'")
    return text


def identity_text(value: object) -> str:
    return redis_key_segment_text(value, "identity")


def required_record_content(value: object) -> str:
    text = markdown_text(value, "record_content")
    if not text.strip():
        raise ValueError("record_content must be non-empty")
    return text


def optional_record_content(value: object) -> str:
    if value is None:
        return ""
    return markdown_text(value, "record_content")


def markdown_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be plain or markdown text")
    if "\x00" in value:
        raise ValueError(f"{field_name} must not contain NUL bytes")
    for index, character in enumerate(value):
        codepoint = ord(character)
        if codepoint < 32 and character not in "\t\n\r":
            raise ValueError(f"{field_name} contains an unsupported control character at offset {index}")
    return value


def json_object(value: object, field_name: str) -> JsonObject:
    if value is None:
        return {}
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field_name} must be a JSON object string") from exc
        value = parsed
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    return dict(value)


def json_blob(value: object, field_name: str) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        # Validate but preserve canonical serialization below.
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field_name} must be valid JSON") from exc
        value = parsed
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def dump_json_object(value: JsonObject) -> str:
    return json.dumps(dict(value or {}), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def asset_list(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("assets must be a list")
    return [plain_non_empty_string(item, f"assets[{index}]") for index, item in enumerate(value)]


def populate_identity_from_identifier(value: object) -> object:
    return value


class ExternalUploadRecordMixin:
    """Redis hash dump policy for records created from arbitrary external NDJSON.

    Pydantic keeps unknown keys in model_extra / __pydantic_extra__ when the
    concrete model sets extra="allow". Those keys stay visible in ordinary
    model_dump() output, but Redis receives them as one scalar JSON field named
    baggage so arbitrary source metadata cannot leak into hash fields as dicts
    or lists.
    """

    @property
    def baggage(self) -> JsonObject:
        return dict(getattr(self, "model_extra", None) or {})

    def dump_redis(self) -> dict[str, str]:
        baggage = self.baggage
        dumped = self.model_dump(mode="json", exclude=set(baggage))
        if baggage:
            dumped["baggage"] = dump_json_object(baggage)
        return {key: redis_hash_scalar(value, field_name=key) for key, value in dumped.items()}


def redis_hash_scalar(value: object, *, field_name: str) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)
    raise TypeError(
        f"{field_name} serialized to {type(value).__name__}; "
        "external upload models must dump Redis hashes as scalar strings"
    )


RedisIdentity = Annotated[str, BeforeValidator(identity_text)]
RecordIdentity = Annotated[str, BeforeValidator(record_identity_text)]
RequiredRecordContent = Annotated[str, BeforeValidator(required_record_content)]
OptionalRecordContent = Annotated[str, BeforeValidator(optional_record_content)]
JsonObjectField = Annotated[
    JsonObject,
    BeforeValidator(lambda value: json_object(value, "json object")),
    PlainSerializer(dump_json_object, return_type=str),
]


__all__ = [
    "ExternalUploadRecordMixin",
    "JsonObject",
    "JsonObjectField",
    "OptionalRecordContent",
    "RecordIdentity",
    "RedisIdentity",
    "RequiredRecordContent",
    "asset_list",
    "dump_json_object",
    "identity_text",
    "json_blob",
    "json_object",
    "markdown_text",
    "optional_record_content",
    "optional_text",
    "plain_object",
    "record_identity_text",
    "record_type_text",
    "redis_hash_scalar",
    "required_record_content",
    "required_text",
    "populate_identity_from_identifier",
]
