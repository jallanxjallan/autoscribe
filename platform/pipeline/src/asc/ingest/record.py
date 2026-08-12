from collections.abc import Mapping
from typing import Any

from asc.ingest.common import IngestedItem, IngestInputError
from asc.ingest.handlers import HANDLERS
from asc.ingest.record_types import canonical_record_type, canonical_target

MANDATORY_FIELDS = ("type", "identity", "content", "extra")


def ingest_record(raw_record: object, *, target: str = "all") -> IngestedItem:
    if not isinstance(raw_record, Mapping):
        raise IngestInputError("ingest record must be an object")

    record = dict(raw_record)
    require_ingest_fields(record)

    record_type = canonical_record_type(record["type"])
    expected = canonical_target(target)
    if expected != "all" and record_type != expected:
        raise IngestInputError(f"type {record_type!r} does not match ingest target {expected!r}")

    record["type"] = record_type
    record["identity"] = required_string(record["identity"], "identity")
    record["extra"] = required_extra(record["extra"])

    try:
        handler = HANDLERS[record_type]
    except KeyError as exc:
        known = ", ".join(sorted(HANDLERS))
        raise IngestInputError(f"unsupported type {record_type!r}; known: {known}") from exc

    return handler(record)


def require_ingest_fields(record: Mapping[str, Any]) -> None:
    missing = [field for field in MANDATORY_FIELDS if field not in record]
    if missing:
        raise IngestInputError(f"missing mandatory field(s): {', '.join(missing)}")


def required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IngestInputError(f"{field} must be a non-empty string")
    return value.strip()


def required_extra(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise IngestInputError("extra must be an object")
    return dict(value)


def record_identifier(record: object, *, fallback: str) -> str:
    if isinstance(record, Mapping):
        value = record.get("identity")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


__all__ = ["MANDATORY_FIELDS", "ingest_record", "record_identifier"]
