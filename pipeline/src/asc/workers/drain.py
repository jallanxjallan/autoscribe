"""Drain worker placeholder for the atomic-step queue.

Drain is intentionally non-draining while the worker is still a custody probe;
otherwise requeue-on-claim would create an infinite loop.
"""

from __future__ import annotations

from asc.workers.once import OnceWorker


class DrainWorker(OnceWorker):
    """Run the same single-step custody probe as OnceWorker for now."""

    def __init__(self, *, quiet: bool = False) -> None:
        super().__init__()
        self.quiet = quiet


__all__ = ["DrainWorker"]
