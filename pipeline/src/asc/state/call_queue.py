"""Compatibility shim for the orchestrator call hold queue.

Enqueue submits materialized RuntimeCallRecord keys here. The orchestrator polls
this hold queue, takes ledger custody, then stages the first runtime step.
"""

from __future__ import annotations

from asc.state.call_hold_queue import (
    CALL_HOLD_QUEUE_KEY,
    CallHoldQueue as CallQueue,
    QueuedCall as ClaimedCall,
    call_hold_queue_key,
    claim_call,
    claim_next,
    clear,
    count,
    enqueue,
    enqueue_batch,
    enqueue_call,
    peek_call,
    peek_next,
)

STATE_NAMESPACE = "queue"
CONTROL_DOMAIN = STATE_NAMESPACE
QUEUE_SEGMENT = "hold"
QUEUE_KIND = QUEUE_SEGMENT
CALL_IDENTITY = "orchestrator-call"


def call_queue_key() -> str:
    return CALL_HOLD_QUEUE_KEY


__all__ = [
    "CALL_HOLD_QUEUE_KEY",
    "STATE_NAMESPACE",
    "CONTROL_DOMAIN",
    "QUEUE_SEGMENT",
    "QUEUE_KIND",
    "CALL_IDENTITY",
    "ClaimedCall",
    "CallQueue",
    "call_hold_queue_key",
    "call_queue_key",
    "claim_call",
    "claim_next",
    "clear",
    "count",
    "enqueue",
    "enqueue_batch",
    "enqueue_call",
    "peek_call",
    "peek_next",
]
