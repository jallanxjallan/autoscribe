from __future__ import annotations

import sys
from collections.abc import Iterable
from typing import TextIO

from asc.models.runtime.call import CallRecord
from asc.upload.common import UploadReport, UploadTarget, upload_records_for_target, upload_stream_for_target


def target() -> UploadTarget:
    return UploadTarget(
        name="call",
        aliases=("calls", "document", "documents", "prompt", "prompts"),
        record_type_aliases=("document", "prompt"),
        record_identity_field="source_slug",
        record_content_field="content",
        json_baggage=True,
        model_fields=("type", "identity", "source_slug", "content", "created_at"),
        model_type=CallRecord,
    )


def upload_stream(source: Iterable[str], *, error_stream: TextIO = sys.stderr) -> UploadReport:
    return upload_stream_for_target(source, target=target(), error_stream=error_stream)


def upload_records(records: Iterable[object], *, error_stream: TextIO = sys.stderr) -> UploadReport:
    return upload_records_for_target(records, target=target(), error_stream=error_stream)


__all__ = ["target", "upload_records", "upload_stream"]
