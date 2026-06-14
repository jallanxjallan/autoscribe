from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from asc.state import orchestrator_index, orchestrator_queue, worker_outcome_queue, worker_queue


def claim_outcome(*, block: bool = False, timeout: int = 0) -> Any | None:
    if block:
        return worker_outcome_queue.block_claim_next(timeout=timeout)
    return worker_outcome_queue.claim_next()


def claim_orchestrator_pending(
    *,
    limit: int = 100,
    block: bool = False,
    timeout: int = 0,
) -> list[Any]:
    """Claim orchestrator-pending cursor signals.

    With block=True, wait for at most one item first, then drain up to limit-1
    more without blocking. This keeps the daemon asleep when idle but allows it
    to catch up quickly after a burst.
    """
    if limit <= 0:
        return []

    claimed: list[Any] = []

    if block:
        first = orchestrator_queue.block_claim_next(timeout=timeout)
        if first is None:
            return []
        claimed.append(first)
        remaining = int(limit) - 1
    else:
        remaining = int(limit)

    for _ in range(remaining):
        item = orchestrator_queue.claim_next()
        if item is None:
            break
        claimed.append(item)

    return claimed


def claim_active_stale(
    *,
    limit: int = 25,
    stale_after_seconds: float,
    lease_seconds: float,
) -> list[Any]:
    return orchestrator_index.claim_stale(
        limit=limit,
        stale_after_seconds=stale_after_seconds,
        lease_seconds=lease_seconds,
    )


def enqueue_worker(cursor_key: str) -> int:
    orchestrator_index.touch(cursor_key)
    return worker_queue.enqueue(cursor_key)


def enqueue_orchestrator(cursor_key: str) -> int:
    orchestrator_index.touch(cursor_key)
    return orchestrator_queue.enqueue(cursor_key)


def enqueue_outcome(cursor_key: str) -> int:
    orchestrator_index.touch(cursor_key)
    return worker_outcome_queue.enqueue(cursor_key)


def requeue(cursor_key: str, *, delay_seconds: float = 0.0) -> int:
    """Return a cursor to orchestrator custody.

    Redis LIST queues cannot delay by score. For now, only immediate requeue is
    supported here; delayed retry belongs in a separate scheduler/active-index
    path that moves due items back into a LIST.
    """
    if float(delay_seconds) > 0:
        orchestrator_index.reschedule(cursor_key, delay_seconds=delay_seconds)
        return 1
    return enqueue_orchestrator(cursor_key)


def requeue_many(cursor_keys: Iterable[str]) -> int:
    total = 0
    for cursor_key in cursor_keys:
        total += enqueue_orchestrator(cursor_key)
    return total


__all__ = [
    "claim_active_stale",
    "claim_orchestrator_pending",
    "claim_outcome",
    "enqueue_orchestrator",
    "enqueue_outcome",
    "enqueue_worker",
    "requeue",
    "requeue_many",
]
