from collections.abc import Mapping
from typing import Any

from asc.ingest.common import IngestedItem
from asc.ingest.handlers import HANDLERS
from asc.ingest.record_types import canonical_record_type, canonical_target

MANDATORY_FIELDS = ("record_type", "record_identity", "record_content")
SERVER_IDENTITY_FIELDS = ("identity",)


def ingest_record(raw_record: object, *, target: str = "all") -> IngestedItem:
    if not isinstance(raw_record, Mapping):
        raise TypeError("ingest record must be an object")

    record = dict(raw_record)
    require_ingest_fields(record)

    record_type = canonical_record_type(record["record_type"])
    expected = canonical_target(target)
    if expected != "all" and record_type != expected:
        raise ValueError(f"record_type {record_type!r} does not match ingest target {expected!r}")

    record["record_type"] = record_type
    record["record_identity"] = required_string(record["record_identity"], "record_identity")

    for field_name in SERVER_IDENTITY_FIELDS:
        record.pop(field_name, None)

    try:
        handler = HANDLERS[record_type]
    except KeyError as exc:
        known = ", ".join(sorted(HANDLERS))
        raise ValueError(f"unsupported record_type {record_type!r}; known: {known}") from exc

    return handler(record)


def require_ingest_fields(record: Mapping[str, Any]) -> None:
    missing = [field for field in MANDATORY_FIELDS if field not in record]
    if missing:
        raise ValueError(f"missing mandatory field(s): {', '.join(missing)}")


def required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def record_identifier(record: object, *, fallback: str) -> str:
    if isinstance(record, Mapping):
        value = record.get("record_identity")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


__all__ = ["MANDATORY_FIELDS", "SERVER_IDENTITY_FIELDS", "ingest_record", "record_identifier"]
