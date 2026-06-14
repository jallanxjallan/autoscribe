from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from asc.enqueue.reader import EnqueueRecord


def normalize_enqueue_record(record: object) -> EnqueueRecord:
    if isinstance(record, EnqueueRecord):
        return record

    if isinstance(record, Mapping):
        return EnqueueRecord(
            prompt_slug=_required_slug(record, "prompt_slug"),
            plan_slug=_required_slug(record, "plan_slug"),
            raw_record=record,
        )

    raise TypeError("enqueue record must be a mapping or EnqueueRecord")


def enqueue_record_identifier(record: object, *, fallback: str) -> str:
    try:
        dispatch = normalize_enqueue_record(record)
    except Exception:
        return fallback
    return dispatch.prompt_slug


def _required_slug(record: Mapping[str, Any], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"enqueue record must include {field}")
    return value.strip()


__all__ = ["enqueue_record_identifier", "normalize_enqueue_record"]
