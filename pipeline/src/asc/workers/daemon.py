from __future__ import annotations

import logging
import time
from typing import Any
import sys

from asc.state import worker_queue
from asc.workers.execute import WorkerExecutor

log = logging.getLogger(__name__)

IDLE_SLEEP_SECONDS = 0.25


class WorkerDaemon:
    """Long-lived worker process over full RuntimeCursor keys."""

    def __init__(self, *, idle_sleep_seconds: float = IDLE_SLEEP_SECONDS) -> None:
        self.executor = WorkerExecutor()
        self.idle_sleep_seconds = float(idle_sleep_seconds)

    def run_forever(self) -> None:
        
        while True:
            print("[worker:daemon] claim_next", flush=True)
            print("[worker:daemon] before claim_next", flush=True)
            claimed = worker_queue.claim_next()
            print(f"[worker:daemon] after claim_next claimed={claimed!r}", flush=True)

            if claimed is None:
                print("[worker:daemon] idle", flush=True)
                time.sleep(self.idle_sleep_seconds)
                continue

            print(f"[worker:daemon] claimed={claimed!r}", flush=True)

            cursor_key = _claimed_key(claimed)
            print(f"[worker:daemon] cursor_key={cursor_key}", flush=True)

            print(f"[worker:daemon] before execute cursor={cursor_key}", flush=True)
            self.executor.execute(cursor_key)
            print(f"[worker:daemon] after execute cursor={cursor_key}", flush=True)


def _claimed_key(claimed: Any) -> str:
    value = getattr(claimed, "key", None)

    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"worker queue claim must provide .key, got {claimed!r}")

    return value.strip()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    WorkerDaemon().run_forever()


if __name__ == "__main__":
    main()


__all__ = ["IDLE_SLEEP_SECONDS", "WorkerDaemon"]
