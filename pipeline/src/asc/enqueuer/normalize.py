from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from asc.enqueuer.reader import EnqueueRecord


def normalize_enqueue_record(record: object) -> EnqueueRecord:
    if isinstance(record, EnqueueRecord):
        return record

    if isinstance(record, Mapping):
        return EnqueueRecord(
            call_slug=_required_call_slug(record),
            plan_slug=_required_slug(record, "plan_slug"),
            raw_record=record,
        )

    raise TypeError("enqueue record must be a mapping or EnqueueRecord")


def enqueue_record_identifier(record: object, *, fallback: str) -> str:
    try:
        dispatch = normalize_enqueue_record(record)
    except Exception:
        return fallback
    return dispatch.call_slug


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


__all__ = ["enqueue_record_identifier", "normalize_enqueue_record"]
