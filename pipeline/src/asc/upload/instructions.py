from __future__ import annotations

import sys
from collections.abc import Iterable
from typing import TextIO

from asc.models.control.instruction import InstructionRecord
from asc.upload.common import UploadReport, UploadTarget, upload_records_for_target, upload_stream_for_target


def target() -> UploadTarget:
    return UploadTarget(
        name="instruction",
        aliases=("instructions",),
        record_identity_field="slug",
        record_content_field="content",
        model_type=InstructionRecord,
    )


def upload_stream(source: Iterable[str], *, error_stream: TextIO = sys.stderr) -> UploadReport:
    return upload_stream_for_target(source, target=target(), error_stream=error_stream)


def upload_records(records: Iterable[object], *, error_stream: TextIO = sys.stderr) -> UploadReport:
    return upload_records_for_target(records, target=target(), error_stream=error_stream)


__all__ = ["target", "upload_records", "upload_stream"]
