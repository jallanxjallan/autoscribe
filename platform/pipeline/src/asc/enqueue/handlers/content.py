"""Legacy import location retained for callers that enqueue resolved records directly."""

from asc.enqueue.service import enqueue_record as enqueue_content

__all__ = ["enqueue_content"]
