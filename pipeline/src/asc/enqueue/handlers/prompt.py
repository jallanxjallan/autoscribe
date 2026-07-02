from collections.abc import Mapping
from typing import Any

from asc.enqueue.handlers.content import enqueue_content
from asc.enqueue.report import EnqueuedCall


def enqueue_prompt(record: Mapping[str, Any]) -> EnqueuedCall:
    return enqueue_content(record)


__all__ = ["enqueue_prompt"]
