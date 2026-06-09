from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, TextIO

from asc.streams.ndjson import iter_ndjson_records


@dataclass(frozen=True, slots=True)
class EnqueueRecord:
    prompt_slug: str
    plan_slug: str
    raw_record: Mapping[str, Any]


def iter_enqueue_records(stream: TextIO) -> Iterator[EnqueueRecord]:
    """Yield validated lightweight prompt/plan dispatch records."""

    seen = False
    for parsed in iter_ndjson_records(stream):
        seen = True
        raw = parsed.record

        if not isinstance(raw, Mapping):
            raise ValueError(
                f"enqueue stream row {parsed.line_number} must be a JSON object"
            )

        try:
            yield EnqueueRecord(
                prompt_slug=_required_slug(raw, "prompt_slug"),
                plan_slug=_required_slug(raw, "plan_slug"),
                raw_record=raw,
            )
        except Exception as exc:
            raise ValueError(
                f"invalid enqueue record on line {parsed.line_number}: {exc}"
            ) from exc

    if not seen:
        raise ValueError("no enqueue records found")


def load_enqueue_records(stream: TextIO) -> list[EnqueueRecord]:
    return list(iter_enqueue_records(stream))


def _required_slug(record: Mapping[str, Any], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"enqueue record must include {field}")
    return value.strip()


__all__ = [
    "EnqueueRecord",
    "iter_enqueue_records",
    "load_enqueue_records",
]
