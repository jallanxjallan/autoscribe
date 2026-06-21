"""Worker daemon entrypoint.

Command-line behavior:

    python -m asc.workers.daemon

runs one worker claim cycle and exits.

Imported behavior:

    from asc.workers.daemon import run_forever

runs the long-lived daemon loop.
"""

from __future__ import annotations

from dataclasses import dataclass

from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, configure_logging, run_daemon

from .runtime import run_once as _run_once_raw


@dataclass(frozen=True, slots=True)
class WorkerRunReport:
    claimed: bool


def run_once(
    *,
    timeout: int | None = None,
    empty_limit: int | None = None,
    wait: bool = False,
) -> WorkerRunReport:
    """Wrap the runtime's bare claim result so this conforms to RunReport.

    This only wraps the existing return value — it doesn't change what
    `.runtime.run_once` actually returns. If the runtime carries more
    detail (job key, cursor, etc.) that isn't being surfaced here, that's
    a `workers/runtime.py` change, not something this wrapper invents.
    """

    claimed = _run_once_raw(timeout=timeout, empty_limit=empty_limit, wait=wait)
    return WorkerRunReport(claimed=bool(claimed))


def run_forever(
    *,
    timeout: int = DEFAULT_CLAIM_TIMEOUT_SECONDS,
    empty_limit: int | None = None,
) -> None:
    """Run the worker daemon loop until idle shutdown or interruption."""

    configure_logging()
    run_daemon(
        name="worker",
        run_once=run_once,
        timeout=timeout,
        empty_limit=empty_limit,
    )


def main() -> None:
    """Run one worker cycle from the command line."""

    configure_logging()
    report = run_once(timeout=0, empty_limit=0, wait=False)
    print(f"worker claimed={report.claimed}")


if __name__ == "__main__":
    main()


__all__ = ["WorkerRunReport", "main", "run_forever", "run_once"]