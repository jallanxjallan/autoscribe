from __future__ import annotations

import logging

from asc.state import worker_queue
from asc.workers.execute import WorkerExecutor

log = logging.getLogger(__name__)

# Use a finite timeout rather than BLPOP 0 so a production supervisor can add
# shutdown checks later without changing the queue contract. While blocked in
# Redis this process consumes no Python-loop CPU.
BLOCK_TIMEOUT_SECONDS = 30


class WorkerDaemon:
    """Long-lived worker process over full RuntimeCursor keys.

    The worker queue is a Redis LIST. block_claim() is intentionally blocking:
    idle workers sleep inside Redis/socket I/O instead of polling in Python.
    """

    def __init__(self, *, block_timeout_seconds: int = BLOCK_TIMEOUT_SECONDS) -> None:
        self.executor = WorkerExecutor()
        self.block_timeout_seconds = int(block_timeout_seconds)

    def run_forever(self) -> None:
        while True:
            claimed = worker_queue.block_claim(timeout=self.block_timeout_seconds)
            if claimed is None:
                # Timeout expiry is not work and not an error. Loop quietly.
                continue

            cursor_key = claimed.cursor_key
            log.info("worker claimed cursor=%s", cursor_key)
            self.executor.execute(cursor_key)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    WorkerDaemon().run_forever()


if __name__ == "__main__":
    main()


__all__ = ["BLOCK_TIMEOUT_SECONDS", "WorkerDaemon"]
