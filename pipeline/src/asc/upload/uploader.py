from __future__ import annotations

import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import TextIO, TypeVar

from pydantic import BaseModel, ValidationError

from asc.models.control.instruction import InstructionRecord
from asc.models.control.plan import PlanRecord
from asc.models.uploaded.record import UploadedRecord
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
    save_record: Callable[[RedisModel], UploadedItem] | None = None

    @property
    def names(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)


UPLOAD_TARGETS: dict[str, UploadTarget] = {}


def _register_target(target: UploadTarget) -> None:
    for name in target.names:
        UPLOAD_TARGETS[name] = target


_register_target(
    UploadTarget(
        name="instruction",
        aliases=("instructions",),
        model_type=InstructionRecord,
    )
)
_register_target(
    UploadTarget(
        name="plan",
        aliases=("plans",),
        model_type=PlanRecord,
        save_record=lambda record: _save_plan_record(_as_plan(record)),
    )
)
_register_target(
    UploadTarget(
        name="call",
        aliases=("calls", "document", "documents", "prompt", "prompts"),
        model_type=UploadedRecord,
    )
)


# Reserved now so the CLI can expose `asc upload assets` without inventing a
# separate uploader later. This deliberately fails loudly until the model exists.
ASSET_TARGET_NAMES = {"asset", "assets"}


def upload_instructions_stream(source: Iterable[str], *, error_stream: TextIO = sys.stderr) -> UploadReport:
    return upload_stream(source, target="instructions", error_stream=error_stream)


def upload_plans_stream(source: Iterable[str], *, error_stream: TextIO = sys.stderr) -> UploadReport:
    return upload_stream(source, target="plans", error_stream=error_stream)


def upload_calls_stream(source: Iterable[str], *, error_stream: TextIO = sys.stderr) -> UploadReport:
    return upload_stream(source, target="calls", error_stream=error_stream)


def upload_assets_stream(source: Iterable[str], *, error_stream: TextIO = sys.stderr) -> UploadReport:
    raise NotImplementedError("asset upload is reserved for future support")


def upload_stream(
    source: Iterable[str],
    *,
    target: str,
    error_stream: TextIO = sys.stderr,
) -> UploadReport:
    """Upload one explicitly targeted NDJSON stream.

    This is the single upload dispatcher behind the desired CLI shape:

        asc upload instructions
        asc upload calls
        asc upload plans
        asc upload assets  # reserved, not implemented yet

    The target chooses the model. Incoming NDJSON is passed directly to that
    model; each model owns its public upload contract and validation rules.
    Bad records are reported to stderr and skipped. Malformed NDJSON is a fatal
    stream error because the caller cannot safely continue parsing the stream.
    """

    upload_target = upload_target_for_name(target)
    saved: list[UploadedItem] = []
    skipped: list[SkippedUpload] = []
    by_type: dict[str, int] = {}

    try:
        for parsed in iter_ndjson_records(source):
            location = f"line {parsed.line_number}"
            try:
                record = validate_upload_record(
                    parsed.record,
                    model_type=upload_target.model_type,
                    location=location,
                )
                item = save_upload_record(record, target=upload_target)
            except Exception as exc:
                identifier = record_identifier(parsed.record, fallback=location)
                skipped.append(
                    SkippedUpload(
                        target=upload_target.name,
                        location=location,
                        identifier=identifier,
                        error=str(exc),
                    )
                )
                print(
                    f"[upload:{upload_target.name}] skipping {location} "
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


def upload_records(
    records: Iterable[object],
    *,
    target: str,
    error_stream: TextIO = sys.stderr,
) -> UploadReport:
    """Upload already parsed records through the same target dispatcher."""

    upload_target = upload_target_for_name(target)
    saved: list[UploadedItem] = []
    skipped: list[SkippedUpload] = []
    by_type: dict[str, int] = {}

    for record_number, value in enumerate(records, start=1):
        location = f"record {record_number}"
        try:
            record = validate_upload_record(value, model_type=upload_target.model_type, location=location)
            item = save_upload_record(record, target=upload_target)
        except Exception as exc:
            identifier = record_identifier(value, fallback=location)
            skipped.append(
                SkippedUpload(
                    target=upload_target.name,
                    location=location,
                    identifier=identifier,
                    error=str(exc),
                )
            )
            print(
                f"[upload:{upload_target.name}] skipping {location} "
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


def upload_target_for_name(name: str) -> UploadTarget:
    normalized = name.strip().lower().replace("_", "-")
    if normalized in ASSET_TARGET_NAMES:
        raise NotImplementedError("asset upload is reserved for future support")

    target = UPLOAD_TARGETS.get(normalized)
    if target is None:
        known = sorted(set(UPLOAD_TARGETS) | ASSET_TARGET_NAMES)
        raise ValueError(f"unknown upload target {name!r}; known: {', '.join(known)}")
    return target


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


def save_upload_record(record: RedisModel, *, target: UploadTarget | None = None) -> UploadedItem:
    upload_target = target or upload_target_for_record(record)

    if upload_target.save_record is not None:
        return upload_target.save_record(record)

    full_key = str(record.save())
    slug = record_identity(record)
    SlugMap().set(slug, full_key)
    return UploadedItem(target=upload_target.name, slug=slug, key=full_key)


def upload_target_for_record(record: RedisModel) -> UploadTarget:
    if isinstance(record, InstructionRecord):
        return upload_target_for_name("instruction")
    if isinstance(record, PlanRecord):
        return upload_target_for_name("plan")
    if isinstance(record, UploadedRecord):
        return upload_target_for_name("call")
    raise TypeError(f"unsupported upload record model: {type(record).__name__}")


def record_identity(record: object) -> str:
    value = getattr(record, "record_identity", None)
    if isinstance(value, str) and value.strip():
        return value.strip()

    value = getattr(record, "slug", None)
    if isinstance(value, str) and value.strip():
        return value.strip()

    raise ValueError(f"{type(record).__name__} does not expose record_identity or slug")


def record_identifier(record: object, *, fallback: str) -> str:
    if isinstance(record, BaseModel):
        return record_identifier(record.model_dump(mode="json"), fallback=fallback)

    if isinstance(record, dict):
        for field in (
            "record_identity",
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


def _as_plan(record: RedisModel) -> PlanRecord:
    if not isinstance(record, PlanRecord):
        raise TypeError(f"expected PlanRecord, got {type(record).__name__}")
    return record


def _save_plan_record(record: PlanRecord) -> UploadedItem:
    upload_plan_record(record.plan_dict())
    return UploadedItem(target="plan", slug=record.record_identity, key=record.key())


# Compatibility aliases for older callers/tests.
def upload_typed_control_stream(
    source: Iterable[str],
    *,
    target: str,
    error_stream: TextIO = sys.stderr,
) -> UploadReport:
    return upload_stream(source, target=target, error_stream=error_stream)


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
    return validate_upload_record(record, model_type=model_type, location=location)


def save_control_record(record: RedisModel) -> None:
    save_upload_record(record)


CONTROL_MODELS: dict[str, UploadModel] = {
    "instruction": InstructionRecord,
    "plan": PlanRecord,
}
CONTROL_TARGETS: dict[str, str] = {
    "instructions": "instruction",
    "plans": "plan",
    "instruction": "instruction",
    "plan": "plan",
}


def control_model_for_target(target: str) -> tuple[str, UploadModel]:
    upload_target = upload_target_for_name(target)
    if upload_target.name not in CONTROL_MODELS:
        known = ", ".join(sorted(CONTROL_TARGETS))
        raise ValueError(f"unknown control upload target {target!r}; known: {known}")
    return upload_target.name, upload_target.model_type


__all__ = [
    "ASSET_TARGET_NAMES",
    "CONTROL_MODELS",
    "CONTROL_TARGETS",
    "SkippedUpload",
    "UPLOAD_TARGETS",
    "UploadReport",
    "UploadTarget",
    "UploadedItem",
    "control_model_for_target",
    "record_identifier",
    "record_identity",
    "save_control_record",
    "save_upload_record",
    "upload_assets_stream",
    "upload_calls_stream",
    "upload_instructions_stream",
    "upload_plans_stream",
    "upload_records",
    "upload_stream",
    "upload_target_for_name",
    "upload_target_for_record",
    "upload_typed_control_stream",
    "validate_control_record",
    "validate_typed_control_record",
    "validate_upload_record",
]
