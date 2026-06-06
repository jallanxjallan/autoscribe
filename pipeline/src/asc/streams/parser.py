from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from asc.streams.ndjson import iter_ndjson_records


RAW_RECORD_FIELD = "raw_record"


@dataclass(frozen=True)
class ParsedStreamRecord:
    line_number: int
    raw_record: dict[str, Any]
    flat_record: dict[str, Any]


def flatten_mapping(
    record: Mapping[str, Any],
    *,
    separator: str = ".",
) -> dict[str, Any]:
    """
    Mechanically flatten nested mapping keys while preserving top-level keys.

    Example:

        {"metadata": {"title": "Foo"}}

    becomes:

        {
            "metadata": {"title": "Foo"},
            "metadata.title": "Foo",
        }

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
    "RAW_RECORD_FIELD",
    "ParsedStreamRecord",
    "flatten_mapping",
    "iter_flat_stream_records",
    "prepare_stream_record",
]
