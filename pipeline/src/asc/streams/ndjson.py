from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, TextIO


class NdjsonParseError(ValueError):
    """Raised when a stream cannot be read as NDJSON objects."""


@dataclass(frozen=True)
class ParsedNdjsonLine:
    line_number: int
    record: dict[str, Any]


def iter_ndjson_records(lines: Iterable[str]) -> Iterator[ParsedNdjsonLine]:
    """
    Yield nonblank NDJSON lines as JSON objects.

    This module owns stream mechanics only. It does not validate AutoScribe
    semantics, infer record types, or normalize producer-specific shapes.
    """
    for line_number, line in enumerate(lines, start=1):
        text = line.strip()

        if not text:
            continue

        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise NdjsonParseError(
                f"invalid JSON on line {line_number}: {exc.msg}"
            ) from exc

        if not isinstance(value, dict):
            raise NdjsonParseError(
                f"invalid NDJSON object on line {line_number}: "
                f"expected object, got {type(value).__name__}"
            )

        yield ParsedNdjsonLine(line_number=line_number, record=value)


def dump_ndjson_record(record: Mapping[str, Any]) -> str:
    """Return one compact JSON object suitable for an NDJSON line."""
    try:
        return json.dumps(dict(record), ensure_ascii=False, separators=(",", ":"))
    except TypeError as exc:
        raise TypeError("record is not JSON serializable") from exc


def write_ndjson_record(record: Mapping[str, Any], stream: TextIO) -> None:
    """Write one mapping as one NDJSON line."""
    stream.write(dump_ndjson_record(record))
    stream.write("\n")


def write_ndjson_records(records: Iterable[Mapping[str, Any]], stream: TextIO) -> int:
    """Write mappings as NDJSON and return the number of records emitted."""
    count = 0
    for record in records:
        write_ndjson_record(record, stream)
        count += 1
    return count


__all__ = [
    "NdjsonParseError",
    "ParsedNdjsonLine",
    "dump_ndjson_record",
    "iter_ndjson_records",
    "write_ndjson_record",
    "write_ndjson_records",
]
