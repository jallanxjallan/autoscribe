from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

from asc.models.helpers.plain import plain_non_empty_string, slug_like_text


IdentifierKind = Literal["slug", "uri", "external_id"]
JsonRecord = dict[str, Any]

_IDENTIFIER_FIELD_BY_KIND: dict[str, str] = {
    "slug": "slug",
    "uri": "uri",
    "external_id": "external_id",
}


@dataclass(frozen=True)
class IdentifierClassification:
    kind: IdentifierKind
    field_name: str
    value: str


class UploadRecordError(ValueError):
    """Raised when an upload stream record violates the intake contract."""



def parse_json_object_line(line: str, *, line_number: int | None = None) -> JsonRecord:
    """
    Parse one NDJSON line into a Python dict.

    This is intentionally boring: the stream layer confirms valid JSON object
    shape and does not rescue, alias, or recursively extract model fields.
    """
    try:
        value = json.loads(line)
    except json.JSONDecodeError as error:
        prefix = f"line {line_number}: " if line_number is not None else ""
        raise UploadRecordError(f"{prefix}invalid JSON: {error.msg}") from error

    if not isinstance(value, dict):
        prefix = f"line {line_number}: " if line_number is not None else ""
        raise UploadRecordError(f"{prefix}expected JSON object")

    return value



def require_top_level_text(record: Mapping[str, Any], field_name: str) -> str:
    value = record.get(field_name)
    try:
        return plain_non_empty_string(value, field_name).strip()
    except ValueError as error:
        raise UploadRecordError(f"upload record requires top-level {field_name!r}") from error



def require_record_type(
    record: Mapping[str, Any],
    *,
    allowed_types: Collection[str] | None = None,
) -> str:
    record_type = require_top_level_text(record, "type")

    if allowed_types is not None and record_type not in allowed_types:
        allowed = ", ".join(sorted(allowed_types))
        raise UploadRecordError(
            f"upload record type {record_type!r} is not registered; expected one of: {allowed}"
        )

    return record_type



def require_identifier(record: Mapping[str, Any]) -> str:
    return require_top_level_text(record, "identifier")



def classify_identifier(
    identifier: object,
    *,
    allowed_kinds: Collection[IdentifierKind],
) -> IdentifierClassification:
    """
    Classify a canonical top-level identifier into a specific identity field.

    A slug-shaped value is promoted to slug only for types that explicitly allow
    slug identifiers. Otherwise, if external_id is allowed, it remains opaque.
    """
    text = plain_non_empty_string(identifier, "identifier").strip()

    if "slug" in allowed_kinds and _is_slug(text):
        return IdentifierClassification(kind="slug", field_name="slug", value=text)

    if "uri" in allowed_kinds and _is_uri(text):
        return IdentifierClassification(kind="uri", field_name="uri", value=text)

    if "external_id" in allowed_kinds:
        return IdentifierClassification(
            kind="external_id",
            field_name="external_id",
            value=text,
        )

    allowed = ", ".join(sorted(allowed_kinds))
    raise UploadRecordError(
        f"identifier {text!r} does not match the allowed identifier kinds: {allowed}"
    )



def prepare_upload_record(
    value: object,
    *,
    allowed_types: Collection[str] | None = None,
    identifier_kinds: Collection[IdentifierKind] = ("slug", "uri", "external_id"),
    preserve_raw: bool = True,
    raw_field: str = "raw_record",
    strip_runtime_identity: bool = True,
) -> object:
    """
    Prepare an upload record without normalizing model fields.

    The only derived fields are identity fields based on the canonical top-level
    identifier, for example identifier -> slug, uri, or external_id.

    This helper deliberately does not recursively search for client/content/etc.
    Those remain provider/model contracts.
    """
    if not isinstance(value, Mapping):
        return value

    original = dict(value)
    prepared: JsonRecord = dict(value)

    require_record_type(prepared, allowed_types=allowed_types)
    identifier = require_identifier(prepared)
    classification = classify_identifier(identifier, allowed_kinds=identifier_kinds)

    prepared["identifier"] = classification.value
    prepared["identifier_kind"] = classification.kind
    prepared.setdefault(classification.field_name, classification.value)

    if preserve_raw:
        prepared.setdefault(raw_field, original)

    if strip_runtime_identity:
        prepared.pop("identity", None)

    return prepared



def _is_slug(value: str) -> bool:
    try:
        slug_like_text(value)
    except ValueError:
        return False
    return True



def _is_uri(value: str) -> bool:
    parsed = urlparse(value)

    if not parsed.scheme:
        return False

    if parsed.scheme in {"http", "https"}:
        return bool(parsed.netloc)

    return bool(parsed.path or parsed.netloc)


__all__ = [
    "IdentifierClassification",
    "IdentifierKind",
    "JsonRecord",
    "UploadRecordError",
    "classify_identifier",
    "parse_json_object_line",
    "prepare_upload_record",
    "require_identifier",
    "require_record_type",
    "require_top_level_text",
]
