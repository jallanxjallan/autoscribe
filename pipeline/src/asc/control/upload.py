from __future__ import annotations

import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TextIO, TypeVar

from pydantic import ValidationError

from asc.models.control.instruction import InstructionRecord
from asc.models.control.plan import PlanRecord
from asc.redis.model_base import RedisModel
from asc.state.slugmap import SlugMap
from asc.streams.ndjson import NdjsonParseError, iter_ndjson_records
from asc.control.plan_steps import upload_plan_record

ControlRecord = InstructionRecord | PlanRecord
ControlModel = type[ControlRecord]
TControl = TypeVar("TControl", bound=RedisModel)

CONTROL_MODELS: dict[str, ControlModel] = {
    "instruction": InstructionRecord,
    "plan": PlanRecord,
}

CONTROL_TARGETS: dict[str, str] = {
    "instructions": "instruction",
    "plans": "plan",
    "instruction": "instruction",
    "plan": "plan",
}


@dataclass(frozen=True)
class UploadReport:
    record_count: int = 0
    skipped_count: int = 0
    by_type: dict[str, int] = field(default_factory=dict)


def upload_instructions_stream(source: TextIO) -> UploadReport:
    return upload_typed_control_stream(source, target="instructions")


def upload_plans_stream(source: TextIO) -> UploadReport:
    return upload_typed_control_stream(source, target="plans")


def upload_typed_control_stream(
    source: Iterable[str],
    *,
    target: str,
    error_stream: TextIO = sys.stderr,
) -> UploadReport:
    """Upload one explicitly targeted control stream.

    The CLI target chooses the model. Incoming NDJSON is passed directly to
    that model; the model owns the public upload contract and rejects records
    with the wrong record_type or malformed fields.

    Bad records are reported to stderr and skipped. Malformed NDJSON remains a
    fatal stream error.
    """

    record_type, model_type = control_model_for_target(target)
    saved_count = 0
    skipped_count = 0
    by_type: dict[str, int] = {}

    try:
        for parsed in iter_ndjson_records(source):
            try:
                record = validate_control_record(
                    parsed.record,
                    model_type=model_type,
                    location=f"line {parsed.line_number}",
                )
                save_control_record(record)

            except Exception as exc:
                skipped_count += 1
                print(
                    f"[control:upload:{record_type}] skipping line "
                    f"{parsed.line_number}: {exc}",
                    file=error_stream,
                )
                continue

            saved_count += 1
            by_type[record_type] = by_type.get(record_type, 0) + 1

    except NdjsonParseError as exc:
        raise ValueError(str(exc)) from exc

    return UploadReport(
        record_count=saved_count,
        skipped_count=skipped_count,
        by_type=by_type,
    )


def control_model_for_target(target: str) -> tuple[str, ControlModel]:
    record_type = CONTROL_TARGETS.get(target)
    if record_type is None:
        known = ", ".join(sorted(CONTROL_TARGETS))
        raise ValueError(f"unknown control upload target {target!r}; known: {known}")

    model_type = CONTROL_MODELS[record_type]
    return record_type, model_type


def validate_control_record(
    record: object,
    *,
    model_type: type[TControl],
    location: str = "record",
) -> TControl:
    try:
        return model_type.model_validate(record)
    except ValidationError as exc:
        raise ValueError(f"{location}: validation failed: {exc}") from exc


def save_control_record(record: RedisModel) -> None:
    if isinstance(record, PlanRecord):
        upload_plan_record(record.plan_dict())
        return
    
    full_key = record.save()
    SlugMap().set(record.record_identity, full_key)


# Compatibility aliases for older callers/tests.
def validate_typed_control_record(
    record: object,
    *,
    expected_type: str,
    model_type: type[TControl],
    location: str = "record",
) -> TControl:
    return validate_control_record(record, model_type=model_type, location=location)


def _clean_optional_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _record_label(record: RedisModel, *, fallback: str) -> str:
    for attr in ("label", "title", "name"):
        value = getattr(record, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()

    source = getattr(record, "source", None)
    if isinstance(source, dict):
        for key in ("label", "title", "name", "filename", "path"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    description = getattr(record, "description", "")
    if isinstance(description, str) and description.strip():
        return description.strip().splitlines()[0].strip() or fallback

    return fallback


__all__ = [
    "CONTROL_MODELS",
    "CONTROL_TARGETS",
    "UploadReport",
    "control_model_for_target",
    "save_control_record",
    "upload_instructions_stream",
    "upload_plans_stream",
    "upload_typed_control_stream",
    "validate_control_record",
    "validate_typed_control_record",
]
