from __future__ import annotations

import sys
from collections.abc import Iterable
from typing import TextIO

from asc.models.control.plan import PlanRecord
from asc.redis.model_base import RedisModel
from asc.upload.common import UploadedItem, UploadReport, UploadTarget, upload_records_for_target, upload_stream_for_target


def target() -> UploadTarget:
    return UploadTarget(
        name="plan",
        aliases=("plans",),
        record_identity_field="slug",
        record_content_field="content",
        model_type=PlanRecord,
        save_record=_save_plan_record,
    )


def upload_stream(source: Iterable[str], *, error_stream: TextIO = sys.stderr) -> UploadReport:
    return upload_stream_for_target(source, target=target(), error_stream=error_stream)


def upload_records(records: Iterable[object], *, error_stream: TextIO = sys.stderr) -> UploadReport:
    return upload_records_for_target(records, target=target(), error_stream=error_stream)


def _save_plan_record(record: RedisModel) -> UploadedItem:
    if not isinstance(record, PlanRecord):
        raise TypeError(f"expected PlanRecord, got {type(record).__name__}")

    # Plan step materialization is plan-upload specific. Keep this import here
    # so call uploads never load asc.control.plan_steps.
    from asc.control.plan_steps import upload_plan_record

    upload_plan_record(record.plan_dict())
    return UploadedItem(target="plan", slug=record.slug, key=record.key())


__all__ = ["target", "upload_records", "upload_stream"]
