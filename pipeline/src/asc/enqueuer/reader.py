from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, TextIO

from asc.streams.ndjson import iter_ndjson_records


@dataclass(frozen=True, slots=True)
class EnqueueRecord:
    """One run-spec row: one call slug paired with one plan slug.

    ``call_slug`` is canonical. ``prompt_slug`` is accepted only at this stream
    boundary so older run manifests can still be read without leaking the alias
    into the rest of enqueuer.
    """

    call_slug: str
    plan_slug: str
    raw_record: Mapping[str, Any]


def iter_enqueue_records(stream: TextIO) -> Iterator[EnqueueRecord]:
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
                call_slug=_required_call_slug(raw),
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


def _required_call_slug(record: Mapping[str, Any]) -> str:
    value = record.get("call_slug")
    if value is None:
        value = record.get("prompt_slug")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("enqueue record must include call_slug or prompt_slug")
    return value.strip()


def _required_slug(record: Mapping[str, Any], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"enqueue record must include {field}")
    return value.strip()


__all__ = ["EnqueueRecord", "iter_enqueue_records", "load_enqueue_records"]
