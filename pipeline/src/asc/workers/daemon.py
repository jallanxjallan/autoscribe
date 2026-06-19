"""Worker daemon entrypoint.

Command-line behavior:

    python -m asc.workers.daemon

runs one worker claim cycle and exits.

Imported behavior:

    from asc.workers.daemon import run_forever

runs the long-lived daemon loop.
"""

from __future__ import annotations

from asc.state.daemon import run_daemon

from .runtime import run_once


def run_forever() -> None:
    """Run the worker daemon loop until idle shutdown or interruption."""

    run_daemon(
        name="worker",
        run_once=run_once,
    )


def main() -> None:
    """Run one worker cycle from the command line."""

    claimed = run_once(timeout=0, empty_limit=0, wait=False)
    print(f"worker claimed={claimed}")


if __name__ == "__main__":
    main()