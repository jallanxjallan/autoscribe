from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, TextIO


RAW_RECORD_FIELD = "raw_record"


class NdjsonParseError(ValueError):
    """Raised when a stream cannot be read as NDJSON objects."""


@dataclass(frozen=True)
class ParsedNdjsonLine:
    line_number: int
    record: dict[str, Any]


@dataclass(frozen=True)
class ParsedStreamRecord:
    line_number: int
    raw_record: dict[str, Any]
    flat_record: dict[str, Any]


def iter_ndjson_records(lines: Iterable[str]) -> Iterator[ParsedNdjsonLine]:
    """Yield nonblank NDJSON lines as JSON objects.

    This owns generic stream mechanics only. It does not validate AutoScribe
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


def flatten_mapping(
    record: Mapping[str, Any],
    *,
    separator: str = ".",
) -> dict[str, Any]:
    """
    Mechanically flatten nested mapping keys while preserving top-level keys.

    Collision rule: explicit keys already present in the record win. Generated
    flattened keys never overwrite producer-emitted keys.
    """
    flat: dict[str, Any] = dict(record)

    def walk(prefix: str, value: Any) -> None:
        if not isinstance(value, Mapping):
            return

        for child_key, child_value in value.items():
            child_path = (
                f"{prefix}{separator}{child_key}"
                if prefix
                else str(child_key)
            )

            if child_path not in flat:
                flat[child_path] = child_value

            walk(child_path, child_value)

    for key, value in record.items():
        walk(str(key), value)

    return flat


def prepare_stream_record(
    record: Mapping[str, Any],
    *,
    separator: str = ".",
    raw_record_field: str = RAW_RECORD_FIELD,
) -> dict[str, Any]:
    """
    Return a flat candidate record for model validation.

    The stream parser does not decide which keys matter. It provides candidates
    and preserves the untouched source object. The target model owns aliases,
    required fields, defaults, and validation.
    """
    flat = flatten_mapping(record, separator=separator)
    flat[raw_record_field] = dict(record)
    return flat


def iter_flat_stream_records(
    lines: Iterable[str],
    *,
    separator: str = ".",
    raw_record_field: str = RAW_RECORD_FIELD,
) -> Iterator[ParsedStreamRecord]:
    """Read NDJSON and yield raw plus flattened stream records."""
    for parsed in iter_ndjson_records(lines):
        yield ParsedStreamRecord(
            line_number=parsed.line_number,
            raw_record=parsed.record,
            flat_record=prepare_stream_record(
                parsed.record,
                separator=separator,
                raw_record_field=raw_record_field,
            ),
        )


__all__ = [
    "NdjsonParseError",
    "ParsedNdjsonLine",
    "ParsedStreamRecord",
    "RAW_RECORD_FIELD",
    "dump_ndjson_record",
    "flatten_mapping",
    "iter_flat_stream_records",
    "iter_ndjson_records",
    "prepare_stream_record",
    "write_ndjson_record",
    "write_ndjson_records",
]
