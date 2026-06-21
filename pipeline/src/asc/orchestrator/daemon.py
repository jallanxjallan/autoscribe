"""Orchestrator entrypoint.

Command-line use runs a single orchestration pass:
    python -m asc.orchestrator.daemon

Long-running daemon use is explicit from an importer:
    from asc.orchestrator.daemon import run_forever
    run_forever()
"""

from __future__ import annotations

from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, configure_logging, run_daemon

from .runtime import OrchestratorRunReport, run_once


def run_forever(
    *,
    timeout: int = DEFAULT_CLAIM_TIMEOUT_SECONDS,
    empty_limit: int | None = None,
) -> None:
    configure_logging()
    run_daemon(
        name="orchestrator",
        run_once=run_once,
        timeout=timeout,
        empty_limit=empty_limit,
    )


def main() -> None:
    configure_logging()
    report = run_once(timeout=0, empty_limit=0, wait=False)
    print(f"orchestrator claimed={report.claimed}")


if __name__ == "__main__":
    main()


__all__ = ["OrchestratorRunReport", "main", "run_forever", "run_once"]
