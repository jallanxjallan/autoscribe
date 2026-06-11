from __future__ import annotations

from dataclasses import dataclass

from asc.state import orchestrator_queue, worker_queue


@dataclass(frozen=True, slots=True)
class ClaimedSignal:
    """One full call_state key claimed from the orchestrator queue."""

    call_state_key: str
    score: float

    @property
    def identity(self) -> str:
        return self.call_state_key


def claim() -> ClaimedSignal | None:
    """Claim one full call_state key for orchestrator handling."""

    claimed = orchestrator_queue.claim_next()
    if claimed is None:
        return None
    return ClaimedSignal(call_state_key=claimed.call_state_key, score=claimed.score)


def enqueue_orchestrator(call_state_key: str, *, score: float | None = None) -> int:
    """Submit or return a full call_state key to the single orchestrator queue."""

    return orchestrator_queue.enqueue(call_state_key, score=score)


def requeue(call_state_key: str, *, score: float | None = None) -> int:
    """Requeue a full call_state key after orchestrator infrastructure failure."""

    return enqueue_orchestrator(call_state_key, score=score)


def enqueue_worker(call_state_key: str, *, score: float | None = None) -> int:
    """Hand a full call_state key to worker custody."""

    return worker_queue.enqueue(call_state_key, score=score)


__all__ = [
    "ClaimedSignal",
    "claim",
    "enqueue_orchestrator",
    "enqueue_worker",
    "requeue",
]
