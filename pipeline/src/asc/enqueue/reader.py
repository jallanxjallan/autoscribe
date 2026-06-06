from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
import json
import sys
from typing import Any, TextIO

from asc.streams.ndjson import iter_ndjson_records
from asc.models.helpers.plain import plain_non_empty_string


ErrorHandler = Callable[[str], None]


def _print_error(message: str) -> None:
    print(message, file=sys.stderr)


def require_stream_identity(
    record: object,
    *,
    allowed_types: set[str] | None = None,
) -> dict[str, Any]:
    """
    Gatekeeper for raw upload/enqueue rows.

    This validates only the global stream contract. Domain-specific required
    fields are left to the model that materializes the row.
    """

    if not isinstance(record, Mapping):
        raise ValueError("stream record must be a JSON object")

    loaded = dict(record)
    record_type = plain_non_empty_string(loaded.get("type"), "type")
    plain_non_empty_string(loaded.get("identifier"), "identifier")

    if allowed_types is not None and record_type not in allowed_types:
        allowed = ", ".join(sorted(allowed_types))
        raise ValueError(f"unsupported stream record type: {record_type!r}; expected one of: {allowed}")

    return loaded


def iter_raw_records(
    stream: TextIO,
    *,
    allowed_types: set[str] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield raw NDJSON object rows after the global stream gatekeeper.

    This is the strict reader used by callers that still want a bad row to
    abort the whole stream.
    """

    seen = False
    for raw in iter_ndjson_records(stream):
        seen = True
        yield require_stream_identity(raw, allowed_types=allowed_types)

    if not seen:
        raise ValueError("no records found")


def iter_atomic_raw_records(
    stream: TextIO,
    *,
    allowed_types: set[str] | None = None,
    on_error: ErrorHandler | None = None,
    error_prefix: str = "[enqueue]",
) -> Iterator[dict[str, Any]]:
    """Yield valid raw NDJSON rows and report bad rows without aborting.

    Enqueue uses this reader so each prompt line is handled as an independent
    work item. Malformed JSON, non-object JSON, unsupported record types, and
    missing stream identity fields are reported to stderr and skipped.
    """

    report_error = on_error or _print_error

    for line_number, line in enumerate(stream, start=1):
        stripped = line.strip()
        if not stripped:
            continue

        try:
            raw = json.loads(stripped)
            yield require_stream_identity(raw, allowed_types=allowed_types)
        except Exception as exc:
            report_error(f"{error_prefix} line {line_number}: skipped invalid record: {exc}")
            continue


def load_raw_records(
    stream: TextIO,
    *,
    allowed_types: set[str] | None = None,
) -> list[dict[str, Any]]:
    return list(iter_raw_records(stream, allowed_types=allowed_types))


# Transitional aliases while callers are renamed. These now return raw mappings,
# not UploadedRecord instances.
iter_enqueue_records = iter_raw_records
load_enqueue_records = load_raw_records

__all__ = [
    "iter_atomic_raw_records",
    "iter_raw_records",
    "load_raw_records",
    "iter_enqueue_records",
    "load_enqueue_records",
    "require_stream_identity",
]
