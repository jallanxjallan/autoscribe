"""Orchestrator daemon entrypoint and runtime helpers.

Run once from the command line:
    python -m asc.orchestrator.daemon

Run forever from imported code:
    from asc.orchestrator.daemon import run_forever
    run_forever()
"""

from dataclasses import dataclass

from asc.orchestrator import inbox as orchestrator_inbox
from asc.orchestrator.handle import handle
from asc.orchestrator.post_key import key_kind
from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, configure_logging, run_daemon


@dataclass(frozen=True, slots=True)
class OrchestratorRunReport:
    claimed: bool
    post_key: str | None = None
    kind: str | None = None


def run_once(
    *,
    timeout: int | None = None,
    empty_limit: int | None = None,
    wait: bool = False,
) -> OrchestratorRunReport:
    """Claim and handle one orchestrator inbox message."""

    if wait:
        claimed = orchestrator_inbox.daemon_claim(
            timeout=timeout or 0,
            empty_limit=empty_limit,
        )
    else:
        claimed = orchestrator_inbox.claim()

    if claimed is None:
        return OrchestratorRunReport(claimed=False)

    post_key = str(claimed).strip()
    if not post_key:
        raise ValueError("orchestrator claimed an empty post key")

    kind = key_kind(post_key)
    handle(post_key)

    return OrchestratorRunReport(
        claimed=True,
        post_key=post_key,
        kind=kind,
    )


def run_forever(
    *,
    timeout: int = DEFAULT_CLAIM_TIMEOUT_SECONDS,
    empty_limit: int | None = None,
) -> None:
    """Run the orchestrator daemon loop until idle shutdown or interruption."""

    configure_logging()
    run_daemon(
        name="orchestrator",
        run_once=lambda **kwargs: run_once(wait=True, **kwargs),
        timeout=timeout,
        empty_limit=empty_limit,
    )


def main() -> None:
    """Run one orchestrator cycle from the command line."""

    configure_logging()
    report = run_once()
    print(
        f"orchestrator claimed={report.claimed} "
        f"post_key={report.post_key} kind={report.kind}"
    )


if __name__ == "__main__":
    main()


__all__ = ["OrchestratorRunReport", "main", "run_forever", "run_once"]
