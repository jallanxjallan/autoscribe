from __future__ import annotations

from asc.state.queues import QueueManager

WORKER_INBOX_KEY = "control:worker:inbox"

_inbox = QueueManager(WORKER_INBOX_KEY)


def insert(task_key: str) -> int:
    """Insert a worker task key into the worker inbox."""

    return _inbox.insert(task_key)


def claim() -> str | None:
    """Claim one worker task key without blocking."""

    claimed = _inbox.claim()
    if claimed is None:
        return None
    return str(getattr(claimed, "key", claimed))


def block_claim(*, timeout: int = 0, empty_limit: int | None = None) -> str | None:
    """Claim one worker task key using the blocking daemon path."""

    claimed = _inbox.daemon_claim(timeout=timeout, empty_limit=empty_limit)
    if claimed is None:
        return None
    return str(getattr(claimed, "key", claimed))


# Shared daemon runner vocabulary.
daemon_claim = block_claim


__all__ = [
    "WORKER_INBOX_KEY",
    "block_claim",
    "claim",
    "daemon_claim",
    "insert",
]
