from collections.abc import Mapping
from typing import Any, Callable

from asc.enqueue.handlers.content import enqueue_content
from asc.enqueue.handlers.prompt import enqueue_prompt
from asc.enqueue.report import EnqueuedCall


ENQUEUE_RECORD_TYPES: dict[str, Callable[[Mapping[str, Any]], EnqueuedCall]] = {
    "content": enqueue_content,
    "prompt": enqueue_prompt,
}


def enqueue_record(record: Mapping[str, Any]) -> EnqueuedCall:
    record_type = _required_record_type(record)

    try:
        handler = ENQUEUE_RECORD_TYPES[record_type]
    except KeyError as exc:
        allowed = ", ".join(sorted(ENQUEUE_RECORD_TYPES))
        raise ValueError(f"enqueue record_type must be one of: {allowed}") from exc

    return handler(record)


def _required_record_type(record: Mapping[str, Any]) -> str:
    value = record.get("record_type")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("enqueue record missing required field: record_type")
    return value.strip()


__all__ = ["ENQUEUE_RECORD_TYPES", "enqueue_record"]
