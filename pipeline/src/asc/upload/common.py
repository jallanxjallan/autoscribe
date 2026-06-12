from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, TextIO, TypeVar

from pydantic import BaseModel, ValidationError

from asc.redis.model_base import RedisModel
from asc.state.slugmap import SlugMap
from asc.streams.ndjson import NdjsonParseError, iter_ndjson_records

UploadModel = type[RedisModel]
TUpload = TypeVar("TUpload", bound=RedisModel)


@dataclass(frozen=True)
class UploadedItem:
    target: str
    slug: str
    key: str


@dataclass(frozen=True)
class SkippedUpload:
    target: str
    location: str
    identifier: str
    error: str


@dataclass(frozen=True)
class UploadReport:
    record_count: int = 0
    skipped_count: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    records: tuple[UploadedItem, ...] = ()
    skipped: tuple[SkippedUpload, ...] = ()

    @property
    def call_count(self) -> int:
        return self.by_type.get("call", 0)

    @property
    def document_count(self) -> int:
        # Compatibility for the old documents uploader name.
        return self.call_count

    @property
    def documents(self) -> tuple[str, ...]:
        # Compatibility for older callers that displayed uploaded document slugs.
        return tuple(item.slug for item in self.records if item.target == "call")


@dataclass(frozen=True)
class UploadTarget:
    name: str
    model_type: UploadModel
    aliases: tuple[str, ...] = ()
    record_type_aliases: tuple[str, ...] = ()
    record_identity_field: str | None = None
    record_content_field: str | None = None
    json_baggage: bool = False
    model_fields: tuple[str, ...] = ()
    save_record: Callable[[RedisModel], UploadedItem] | None = None

    @property
    def names(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)

    @property
    def accepted_record_types(self) -> tuple[str, ...]:
        return (self.name, *self.record_type_aliases)


def upload_stream_for_target(
    source: Iterable[str],
    *,
    target: UploadTarget,
    error_stream: TextIO = sys.stderr,
) -> UploadReport:
    """Upload one explicitly targeted NDJSON stream."""

    saved: list[UploadedItem] = []
    skipped: list[SkippedUpload] = []
    by_type: dict[str, int] = {}

    try:
        for parsed in iter_ndjson_records(source):
            location = f"line {parsed.line_number}"
            try:
                normalized = normalize_upload_record(
                    parsed.record,
                    target=target,
                    location=location,
                )
                record = validate_upload_record(
                    normalized,
                    model_type=target.model_type,
                    location=location,
                )
                item = save_upload_record(record, target=target)
            except Exception as exc:
                identifier = record_identifier(parsed.record, fallback=location)
                skipped.append(
                    SkippedUpload(
                        target=target.name,
                        location=location,
                        identifier=identifier,
                        error=str(exc),
                    )
                )
                print(
                    f"[upload:{target.name}] skipping {location} "
                    f"({identifier}): {exc}",
                    file=error_stream,
                )
                continue

            saved.append(item)
            by_type[item.target] = by_type.get(item.target, 0) + 1

    except NdjsonParseError as exc:
        raise ValueError(str(exc)) from exc

    return UploadReport(
        record_count=len(saved),
        skipped_count=len(skipped),
        by_type=by_type,
        records=tuple(saved),
        skipped=tuple(skipped),
    )


def upload_records_for_target(
    records: Iterable[object],
    *,
    target: UploadTarget,
    error_stream: TextIO = sys.stderr,
) -> UploadReport:
    """Upload already parsed records through the same target boundary."""

    saved: list[UploadedItem] = []
    skipped: list[SkippedUpload] = []
    by_type: dict[str, int] = {}

    for record_number, value in enumerate(records, start=1):
        location = f"record {record_number}"
        try:
            normalized = normalize_upload_record(value, target=target, location=location)
            record = validate_upload_record(normalized, model_type=target.model_type, location=location)
            item = save_upload_record(record, target=target)
        except Exception as exc:
            identifier = record_identifier(value, fallback=location)
            skipped.append(
                SkippedUpload(
                    target=target.name,
                    location=location,
                    identifier=identifier,
                    error=str(exc),
                )
            )
            print(
                f"[upload:{target.name}] skipping {location} "
                f"({identifier}): {exc}",
                file=error_stream,
            )
            continue

        saved.append(item)
        by_type[item.target] = by_type.get(item.target, 0) + 1

    return UploadReport(
        record_count=len(saved),
        skipped_count=len(skipped),
        by_type=by_type,
        records=tuple(saved),
        skipped=tuple(skipped),
    )


def normalize_upload_record(
    record: object,
    *,
    target: UploadTarget,
    location: str = "record",
) -> object:
    """Normalize trusted public upload aliases before model validation.

    The public NDJSON ``record_*`` fields are upload dispatcher fields, not
    first-class model fields. After the target/model is known:

    * ``record_type`` is validated against target aliases and then dropped.
    * ``record_identity`` is routed to the model's source slug field.
    * ``record_content`` is routed to the model's ``content`` field.
    """

    if not isinstance(record, Mapping):
        return record

    normalized: dict[str, Any] = dict(record)

    normalize_record_type_alias(normalized, target=target, location=location)
    normalize_record_identity_alias(normalized, target=target, location=location)
    normalize_record_content_alias(normalized, target=target, location=location)
    normalize_json_baggage(normalized, target=target, location=location)

    return normalized


def normalize_record_type_alias(
    record: dict[str, Any],
    *,
    target: UploadTarget,
    location: str,
) -> None:
    """Validate and discard the public record_type/type dispatcher field."""

    raw_type = record.pop("record_type", record.pop("type", target.name))
    if raw_type is None:
        return
    if not isinstance(raw_type, str):
        raise ValueError(f"{location}: record_type must be a string")

    raw_normalized = raw_type.strip().lower()
    accepted = {value.strip().lower() for value in target.accepted_record_types}
    if raw_normalized not in accepted:
        expected = ", ".join(sorted(accepted)) or target.name
        raise ValueError(
            f"{location}: record_type {raw_type!r} is not valid for "
            f"upload target {target.name!r}; expected one of: {expected}"
        )

    if raw_normalized != target.name:
        assert_trusted_upload_source(
            record,
            target=target,
            location=location,
            reason=f"normalize record_type {raw_type!r} to {target.name!r}",
        )
        record.setdefault("source_record_type", raw_type)


def normalize_record_identity_alias(
    record: dict[str, Any],
    *,
    target: UploadTarget,
    location: str,
) -> None:
    """Route record_identity to the model field that owns the source slug."""

    target_field = target.record_identity_field
    if target_field is None:
        return

    has_record_identity = "record_identity" in record
    has_target_field = target_field in record

    if has_record_identity:
        if has_target_field and record[target_field] != record["record_identity"]:
            raise ValueError(f"{location}: record_identity conflicts with {target_field}")
        record[target_field] = record.pop("record_identity")
        return

    # For non-call records, accept legacy slug-shaped inputs at the boundary.
    if target_field != "source_slug" and "slug" in record and not has_target_field:
        record[target_field] = record["slug"]


def normalize_record_content_alias(
    record: dict[str, Any],
    *,
    target: UploadTarget,
    location: str,
) -> None:
    """Route record_content to the canonical model content field."""

    target_field = target.record_content_field
    if target_field is None:
        return

    has_record_content = "record_content" in record
    has_target_field = target_field in record

    if has_record_content:
        if has_target_field and record[target_field] != record["record_content"]:
            raise ValueError(f"{location}: record_content conflicts with {target_field}")
        record[target_field] = record.pop("record_content")


def normalize_json_baggage(
    record: dict[str, Any],
    *,
    target: UploadTarget,
    location: str,
) -> None:
    """Move nested upload baggage into explicit *_json fields.

    Redis hashes may only store scalar strings. Runtime call uploads commonly
    carry provenance such as ``source`` as an object; that data is useful, but
    it must not enter a RedisModel as a raw dict/list extra. Target uploaders
    opt into this behavior so plan records can still validate structured plan
    fields like ``steps`` before their own model serializers run.
    """

    if not target.json_baggage:
        return

    model_fields = set(target.model_fields)

    for field_name in list(record):
        if field_name in model_fields or field_name.endswith("_json"):
            continue

        value = record[field_name]
        if not isinstance(value, (Mapping, list, tuple)):
            continue

        json_field = f"{field_name}_json"
        if json_field in record:
            raise ValueError(f"{location}: {field_name} conflicts with {json_field}")

        assert_trusted_upload_source(
            record,
            target=target,
            location=location,
            reason=f"serialize nested upload baggage {field_name!r} to {json_field!r}",
        )
        record[json_field] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        del record[field_name]


def assert_trusted_upload_source(
    record: Mapping[str, object],
    *,
    target: UploadTarget,
    location: str,
    reason: str,
) -> None:
    """Security checkpoint for upload-boundary record munging.

    This is intentionally a no-op stub for now. Before accepting uploads from
    any untrusted transport, replace this with provenance checks such as a
    signed local manifest, authenticated client identity, allow-listed source
    command, or another explicit trust boundary.
    """

    _ = (record, target, location, reason)


def validate_upload_record(
    record: object,
    *,
    model_type: type[TUpload],
    location: str = "record",
) -> TUpload:
    try:
        return model_type.model_validate(record)
    except ValidationError as exc:
        raise ValueError(f"{location}: validation failed: {exc}") from exc


def save_upload_record(record: RedisModel, *, target: UploadTarget) -> UploadedItem:
    if target.save_record is not None:
        return target.save_record(record)

    full_key = str(record.save())
    slug = record_identity(record)
    SlugMap().set(slug, full_key)
    return UploadedItem(target=target.name, slug=slug, key=full_key)


def record_identity(record: object) -> str:
    for field_name in ("source_slug", "slug", "record_identity"):
        value = getattr(record, field_name, None)
        if isinstance(value, str) and value.strip():
            return value.strip()

    raise ValueError(
        f"{type(record).__name__} does not expose source_slug, slug, or record_identity"
    )


def record_identifier(record: object, *, fallback: str) -> str:
    if isinstance(record, BaseModel):
        return record_identifier(record.model_dump(mode="json"), fallback=fallback)

    if isinstance(record, dict):
        for field in (
            "record_identity",
            "source_slug",
            "prompt_slug",
            "document_slug",
            "slug",
            "identifier",
            "identity",
        ):
            value = record.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return fallback


# Compatibility aliases for older callers/tests that imported validation helpers
# from asc.upload.uploader before target modules were split out.
def validate_control_record(
    record: object,
    *,
    model_type: type[TUpload],
    location: str = "record",
) -> TUpload:
    return validate_upload_record(record, model_type=model_type, location=location)


def validate_typed_control_record(
    record: object,
    *,
    expected_type: str,
    model_type: type[TUpload],
    location: str = "record",
) -> TUpload:
    _ = expected_type
    return validate_upload_record(record, model_type=model_type, location=location)


__all__ = [
    "SkippedUpload",
    "UploadedItem",
    "UploadReport",
    "UploadTarget",
    "assert_trusted_upload_source",
    "normalize_json_baggage",
    "normalize_record_content_alias",
    "normalize_record_identity_alias",
    "normalize_record_type_alias",
    "normalize_upload_record",
    "record_identifier",
    "record_identity",
    "save_upload_record",
    "upload_records_for_target",
    "upload_stream_for_target",
    "validate_control_record",
    "validate_typed_control_record",
    "validate_upload_record",
]
