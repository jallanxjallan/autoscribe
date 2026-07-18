from collections.abc import Mapping
from typing import Any

from asc.ingest.common import IngestedItem, IngestInputError
from asc.ingest.handlers import HANDLERS
from asc.ingest.record_types import canonical_record_type, canonical_target

MANDATORY_FIELDS = ("record_type", "record_identity", "payload")
SERVER_IDENTITY_FIELDS = ("identity",)


def ingest_record(raw_record: object, *, target: str = "all") -> IngestedItem:
    if not isinstance(raw_record, Mapping):
        raise IngestInputError("ingest record must be an object")

    record = dict(raw_record)
    require_ingest_fields(record)

    record_type = canonical_record_type(record["record_type"])
    expected = canonical_target(target)
    if expected != "all" and record_type != expected:
        raise IngestInputError(f"record_type {record_type!r} does not match ingest target {expected!r}")

    record["record_type"] = record_type
    record["record_identity"] = required_string(record["record_identity"], "record_identity")
    record["payload"] = required_payload(record["payload"])

    for field_name in SERVER_IDENTITY_FIELDS:
        record.pop(field_name, None)

    try:
        handler = HANDLERS[record_type]
    except KeyError as exc:
        known = ", ".join(sorted(HANDLERS))
        raise IngestInputError(f"unsupported record_type {record_type!r}; known: {known}") from exc

    return handler(record)


def require_ingest_fields(record: Mapping[str, Any]) -> None:
    missing = [field for field in MANDATORY_FIELDS if field not in record]
    if missing:
        raise IngestInputError(f"missing mandatory field(s): {', '.join(missing)}")


def required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IngestInputError(f"{field} must be a non-empty string")
    return value.strip()


def required_payload(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise IngestInputError("payload must be an object")
    return dict(value)


def record_identifier(record: object, *, fallback: str) -> str:
    if isinstance(record, Mapping):
        value = record.get("record_identity")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


__all__ = [
    "MANDATORY_FIELDS",
    "SERVER_IDENTITY_FIELDS",
    "ingest_record",
    "record_identifier",
]
