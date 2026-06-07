"""Compatibility shim for the retired call queue.

The runtime queue now stores full step keys, not call identities. New code should
import asc.state.runtime_step_queue or asc.state.step_queue directly.
"""

from __future__ import annotations

from asc.state.runtime_step_queue import (
    RUNTIME_STEP_QUEUE_KEY,
    QueuedStep as ClaimedCall,
    RuntimeStepQueue as CallQueue,
    claim_next,
    clear,
    count,
    enqueue_batch,
    enqueue_step,
    peek_next,
    step_queue_key,
)

STATE_NAMESPACE = "queue"
CONTROL_DOMAIN = STATE_NAMESPACE
QUEUE_SEGMENT = "pending"
QUEUE_KIND = QUEUE_SEGMENT
CALL_IDENTITY = "runtime-step"


def call_queue_key() -> str:
    return RUNTIME_STEP_QUEUE_KEY


def enqueue_call(call_identity: str, *, score: float | None = None) -> int:
    return enqueue_step(call_identity, score=score)


def enqueue_member(queue_member: str, *, score: float | None = None) -> int:
    return enqueue_step(queue_member, score=score)


__all__ = [
    "STATE_NAMESPACE",
    "CONTROL_DOMAIN",
    "QUEUE_SEGMENT",
    "QUEUE_KIND",
    "CALL_IDENTITY",
    "ClaimedCall",
    "CallQueue",
    "call_queue_key",
    "claim_next",
    "clear",
    "count",
    "enqueue_batch",
    "enqueue_call",
    "enqueue_member",
    "peek_next",
]
