"""Once worker for the atomic-step queue.

This is intentionally only a custody probe. It claims one queued step key,
immediately requeues it, loads the corresponding Redis value, prints a short
summary, and stops. It does not execute an engine yet.
"""

from __future__ import annotations

from asc.execute.workers.step_probe import StepProbeWorker


class OnceWorker(StepProbeWorker):
    """Claim, requeue, and inspect at most one queued step."""

    # Inherit StepProbeWorker.run(). Do not call the removed old
    # process_next_step() name.
    pass


__all__ = ["OnceWorker"]
