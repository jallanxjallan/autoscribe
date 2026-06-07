from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import TextIO

from asc.streams.ndjson import iter_ndjson_records
from asc.models.uploaded.record import UploadedRecord


def iter_uploaded_records(stream: TextIO) -> Iterator[UploadedRecord]:
    """Yield validated uploaded prompt/chunk records from an NDJSON stream."""

    seen = False
    for parsed in iter_ndjson_records(stream):
        seen = True
        raw = parsed.record

        if not isinstance(raw, Mapping):
            raise ValueError(
                f"enqueue stream row {parsed.line_number} must be a JSON object"
            )

        try:
            yield UploadedRecord.model_validate(raw)
        except Exception as exc:
            raise ValueError(
                f"invalid uploaded prompt on line {parsed.line_number}: {exc}"
            ) from exc

    if not seen:
        raise ValueError("no records found")


def load_uploaded_records(stream: TextIO) -> list[UploadedRecord]:
    return list(iter_uploaded_records(stream))


iter_enqueue_records = iter_uploaded_records
load_enqueue_records = load_uploaded_records

__all__ = [
    "iter_uploaded_records",
    "load_uploaded_records",
    "iter_enqueue_records",
    "load_enqueue_records",
]