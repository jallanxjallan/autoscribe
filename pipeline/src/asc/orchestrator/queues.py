from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from asc.state import orchestrator_index, orchestrator_queue, worker_outcome_queue, worker_queue

ACTIVE_TERMINAL_DELAY_SECONDS = 60.0 * 60.0 * 24.0 * 365.0 * 10.0


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
    """Claim orchestrator-pending cursor signals from the transport queue."""
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


# ---------------------------------------------------------------------------
# Active cursor index helpers
#
# The active cursor index is not a custody queue. It is an observability and
# manual recovery index. Queue operations move work; these helpers record that a
# cursor exists and when it was last observed.
# ---------------------------------------------------------------------------


def register_active_cursor(cursor_key: str) -> None:
    """Add or refresh a cursor in the active cursor index."""
    orchestrator_index.touch(cursor_key)


def touch_active_cursor(cursor_key: str) -> None:
    """Refresh a cursor's active-index score to show recent custody movement."""
    orchestrator_index.touch(cursor_key)


def bump_terminal_cursor(cursor_key: str) -> None:
    """Move a terminal cursor far into the future for forensic visibility."""
    orchestrator_index.reschedule(
        cursor_key,
        delay_seconds=ACTIVE_TERMINAL_DELAY_SECONDS,
    )


def list_stale_active_cursors(
    *,
    limit: int = 25,
    stale_after_seconds: float,
) -> list[Any]:
    """Return stale active cursors for a manual inspection command.

    This helper intentionally does not requeue, lease, retry, or mutate custody.
    A future `asc orchestrator stale` command can call this when someone reports
    a missing response.
    """
    return orchestrator_index.claim_stale(
        limit=limit,
        stale_after_seconds=stale_after_seconds,
        lease_seconds=0.0,
    )


# ---------------------------------------------------------------------------
# Transport queue helpers
# ---------------------------------------------------------------------------


def enqueue_worker(cursor_key: str) -> int:
    touch_active_cursor(cursor_key)
    return worker_queue.enqueue(cursor_key)


def enqueue_orchestrator(cursor_key: str) -> int:
    touch_active_cursor(cursor_key)
    return orchestrator_queue.enqueue(cursor_key)


def enqueue_outcome(cursor_key: str) -> int:
    touch_active_cursor(cursor_key)
    return worker_outcome_queue.enqueue(cursor_key)


def enqueue_orchestrator_many(cursor_keys: Iterable[str]) -> int:
    total = 0
    for cursor_key in cursor_keys:
        total += enqueue_orchestrator(cursor_key)
    return total


__all__ = [
    "ACTIVE_TERMINAL_DELAY_SECONDS",
    "bump_terminal_cursor",
    "claim_orchestrator_pending",
    "claim_outcome",
    "enqueue_orchestrator",
    "enqueue_orchestrator_many",
    "enqueue_outcome",
    "enqueue_worker",
    "list_stale_active_cursors",
    "register_active_cursor",
    "touch_active_cursor",
]
