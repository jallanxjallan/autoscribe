from __future__ import annotations

import sys
from collections.abc import Iterable
from typing import TextIO

from asc.streams.ndjson import NdjsonParseError, iter_ndjson_records
from asc.upload.common import UploadReport
from asc.upload.upload_records import upload_records


def upload_stream(
    source: Iterable[str],
    *,
    target: str,
    error_stream: TextIO = sys.stderr,
) -> UploadReport:
    try:
        records = (parsed.record for parsed in iter_ndjson_records(source))
        return upload_records(records, target=target, error_stream=error_stream)
    except NdjsonParseError as exc:
        raise ValueError(str(exc)) from exc


__all__ = ["upload_stream"]
