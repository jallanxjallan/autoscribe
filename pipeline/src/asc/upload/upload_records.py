import json
import sys
from collections.abc import Iterable, Mapping
from typing import Any, TextIO

from pydantic import ValidationError

from asc.core.identity import generate_identity
from asc.redis.key import RedisKey
from asc.redis.primitives.keys import expire
from asc.state.slugmap import SlugMap
from asc.upload.common import SkippedUpload, UploadedItem, UploadReport
from asc.upload.record_types import canonical_record_type, model_for_record_type

MANDATORY_FIELDS = ("record_type", "record_identity", "record_content")
SERVER_IDENTITY_FIELDS = ("identity",)
PASTURE_TTL_SECONDS = 60 * 60 * 24 * 30


def upload_records(
    records: Iterable[object],
    *,
    target: str,
    error_stream: TextIO = sys.stderr,
) -> UploadReport:
    expected_type = canonical_record_type(target)
    saved: list[UploadedItem] = []
    skipped: list[SkippedUpload] = []
    by_type: dict[str, int] = {}

    for record_number, raw_record in enumerate(records, start=1):
        location = f"record {record_number}"
        try:
            item = upload_record(raw_record, expected_type=expected_type)
        except Exception as exc:
            identifier = record_identifier(raw_record, fallback=location)
            skipped.append(
                SkippedUpload(
                    target=expected_type,
                    location=location,
                    identifier=identifier,
                    error=str(exc),
                )
            )
            print(
                f"[upload:{expected_type}] skipping {location} ({identifier}): {exc}",
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


def upload_record(raw_record: object, *, expected_type: str) -> UploadedItem:
    if not isinstance(raw_record, Mapping):
        raise TypeError("upload record must be an object")

    record = dict(raw_record)
    require_upload_fields(record)

    record_type = canonical_record_type(record["record_type"])
    record_identity = required_string(record["record_identity"], "record_identity")

    expected = canonical_record_type(expected_type)
    if record_type != expected:
        raise ValueError(
            f"record_type {record_type!r} does not match upload target {expected!r}"
        )

    if record_type == "plan":
        return upload_plan_record(record, record_identity=record_identity)

    required_string(record["record_content"], "record_content")

    for field_name in SERVER_IDENTITY_FIELDS:
        record.pop(field_name, None)

    model_class = model_for_record_type(record_type)
    try:
        if hasattr(model_class, "from_ndjson"):
            model = model_class.from_ndjson(record, identity=generate_identity())
        else:
            model = model_class.model_validate(record)
    except ValidationError as exc:
        raise ValueError(f"validation failed: {exc}") from exc

    slugmap = SlugMap()
    old_key = slugmap.get(record_identity)
    new_key = str(model.save())

    slugmap.set(record_identity, new_key)
    if old_key and old_key != new_key:
        expire_key(old_key, PASTURE_TTL_SECONDS)

    return UploadedItem(target=record_type, slug=record_identity, key=new_key)


def expire_key(key: str, ttl_seconds: int) -> None:
    expire(RedisKey(key), int(ttl_seconds))


def upload_plan_record(
    record: Mapping[str, Any],
    *,
    record_identity: str,
) -> UploadedItem:
    content = plan_record_content(record["record_content"])
    plan_identity = generate_identity()
    plan_key = f"plan:{plan_identity}"

    # Fan out first. Do not publish the slugmap pointer unless the executable
    # step set exists. Import lazily so non-plan uploads do not depend on the
    # Step model import path.
    from asc.upload.plan_steps import fanout_plan_steps

    fanout_plan_steps(plan_identity=plan_identity, content=content)

    slugmap = SlugMap()
    slugmap.set(record_identity, plan_key)

    return UploadedItem(target="plan", slug=record_identity, key=plan_key)


def plan_record_content(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)

    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"plan record_content must be a JSON object: {exc}") from exc
        if isinstance(parsed, Mapping):
            return dict(parsed)

    raise ValueError("plan record_content must be a JSON object")


def require_upload_fields(record: Mapping[str, Any]) -> None:
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


__all__ = [
    "MANDATORY_FIELDS",
    "PASTURE_TTL_SECONDS",
    "plan_record_content",
    "upload_plan_record",
    "upload_record",
    "upload_records",
]
