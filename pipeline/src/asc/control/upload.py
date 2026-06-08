from __future__ import annotations

import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, TextIO, TypeVar

from pydantic import ValidationError

from asc.models.control.instruction import InstructionRecord
from asc.models.control.plan import PlanRecord
from asc.redis.model_base import RedisModel
from asc.state.control_slugmap import ControlSlugMap
from asc.streams.ndjson import NdjsonParseError, iter_ndjson_records

ControlRecord = InstructionRecord | PlanRecord
ControlModel = type[ControlRecord]
TControl = TypeVar("TControl", bound=RedisModel)

CONTROL_MODELS: dict[str, ControlModel] = {
    "instruction": InstructionRecord,
    "plan": PlanRecord,
}


@dataclass(frozen=True)
class UploadReport:
    record_count: int = 0
    skipped_count: int = 0
    by_type: dict[str, int] = field(default_factory=dict)


def upload_instructions_stream(source: TextIO) -> UploadReport:
    return upload_typed_control_stream(source, expected_type="instruction")


def upload_plans_stream(source: TextIO) -> UploadReport:
    return upload_typed_control_stream(source, expected_type="plan")


def upload_typed_control_stream(
    source: Iterable[str],
    *,
    expected_type: str,
    error_stream: TextIO = sys.stderr,
) -> UploadReport:
    """
    Upload one explicitly targeted control stream.

    The command chooses the target model. The NDJSON `type` field is retained
    only as a guard so one upload endpoint cannot accidentally consume another
    control type.

    Bad records are reported to stderr and skipped. This keeps producer output
    streams clean and lets one damaged control file avoid poisoning the whole
    upload run.
    """
    model_type = CONTROL_MODELS.get(expected_type)
    if model_type is None:
        known = ", ".join(sorted(CONTROL_MODELS))
        raise ValueError(f"unknown control upload target {expected_type!r}; known: {known}")

    saved_count = 0
    skipped_count = 0
    by_type: dict[str, int] = {}

    try:
        parsed_records = iter_ndjson_records(source)
        for parsed in parsed_records:
            try:
                record = validate_typed_control_record(
                    parsed.record,
                    expected_type=expected_type,
                    model_type=model_type,
                    location=f"line {parsed.line_number}",
                )
                save_control_record(record)

            except Exception as exc:
                skipped_count += 1
                print(
                    f"[control:upload:{expected_type}] skipping line "
                    f"{parsed.line_number}: {exc}",
                    file=error_stream,
                )
                continue

            saved_count += 1
            by_type[expected_type] = by_type.get(expected_type, 0) + 1

    except NdjsonParseError as exc:
        # A malformed JSON line means the stream itself cannot be trusted after
        # this point; unlike model validation, this is a fatal stream error.
        raise ValueError(str(exc)) from exc

    return UploadReport(
        record_count=saved_count,
        skipped_count=skipped_count,
        by_type=by_type,
    )


def validate_typed_control_record(
    record: Mapping[str, Any],
    *,
    expected_type: str,
    model_type: type[TControl],
    location: str = "record",
) -> TControl:
    record_type = record.get("type")

    if record_type != expected_type:
        raise ValueError(
            f"{location}: type={record_type!r} does not match upload target "
            f"{expected_type!r}"
        )

    try:
        return model_type.model_validate(record)
    except ValidationError as exc:
        raise ValueError(f"{location}: validation failed: {exc}") from exc


def save_control_record(record: RedisModel) -> None:
    full_key = record.save()
    ControlSlugMap().bind_record(record, full_key=full_key)


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
    "UploadReport",
    "save_control_record",
    "upload_instructions_stream",
    "upload_plans_stream",
    "upload_typed_control_stream",
    "validate_typed_control_record",
]
