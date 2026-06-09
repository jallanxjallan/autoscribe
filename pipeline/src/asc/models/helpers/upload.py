from __future__ import annotations

import json
from typing import Any

from pydantic import BeforeValidator, PlainSerializer
from typing_extensions import Annotated

from asc.models.helpers.plain import plain_non_empty_string, redis_key_segment_text

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


def record_identity_text(value: object) -> str:
    return redis_key_segment_text(value, "record_identity")


def identity_text(value: object) -> str:
    return redis_key_segment_text(value, "identity")


def required_record_content(value: object) -> str:
    return plain_non_empty_string(value, "record_content")


def optional_record_content(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("record_content must be a plain string")
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
    "optional_record_content",
    "optional_text",
    "plain_object",
    "record_identity_text",
    "required_record_content",
    "required_text",
    "populate_identity_from_identifier",
]
