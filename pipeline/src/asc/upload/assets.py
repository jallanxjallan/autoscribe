from __future__ import annotations

import sys
from collections.abc import Iterable
from typing import TextIO

from asc.upload.common import UploadReport


def upload_stream(source: Iterable[str], *, error_stream: TextIO = sys.stderr) -> UploadReport:
    _ = (source, error_stream)
    raise NotImplementedError("asset upload is reserved for future support")


def upload_records(records: Iterable[object], *, error_stream: TextIO = sys.stderr) -> UploadReport:
    _ = (records, error_stream)
    raise NotImplementedError("asset upload is reserved for future support")


__all__ = ["upload_records", "upload_stream"]
