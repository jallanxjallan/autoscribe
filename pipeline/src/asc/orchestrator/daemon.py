"""Orchestrator daemon entrypoint and runtime helpers.

Run once from the command line:
    python -m asc.orchestrator.daemon

Run forever from imported code:
    from asc.orchestrator.daemon import run_forever
    run_forever()
"""


from dataclasses import dataclass
from typing import Any

from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, configure_logging, run_daemon

from . import inbox
from .contracts import ORCHESTRATOR_POST_KINDS
from .errors import OrchestratorContractError
from .handlers import HANDLERS
from .keys import RuntimeKey


@dataclass(frozen=True, slots=True)
class OrchestratorRunReport:
    claimed: bool


def _claimed_key(claimed: Any) -> str:
    return str(getattr(claimed, "key", claimed)).strip()


def run_once(
    *,
    timeout: int | None = None,
    empty_limit: int | None = None,
    wait: bool = False,
) -> OrchestratorRunReport:
    """Claim and route one orchestrator inbox item."""

    del timeout, empty_limit, wait

    claimed = inbox.claim()
    if claimed is None:
        return OrchestratorRunReport(claimed=False)

    posted = RuntimeKey.parse(_claimed_key(claimed))
    if posted.kind not in ORCHESTRATOR_POST_KINDS:
        expected = ", ".join(sorted(ORCHESTRATOR_POST_KINDS))
        raise OrchestratorContractError(
            f"orchestrator claimed unsupported kind {posted.kind!r}; expected {expected}: {posted.raw}"
        )

    HANDLERS[posted.kind](posted)
    return OrchestratorRunReport(claimed=True)


def run_forever(
    *,
    timeout: int = DEFAULT_CLAIM_TIMEOUT_SECONDS,
    empty_limit: int | None = None,
) -> None:
    """Run the orchestrator daemon loop until idle shutdown or interruption."""

    configure_logging()
    run_daemon(
        name="orchestrator",
        run_once=run_once,
        timeout=timeout,
        empty_limit=empty_limit,
    )


def main() -> None:
    """Run one orchestrator cycle from the command line."""

    configure_logging()
    report = run_once(timeout=0, empty_limit=0, wait=False)
    print(f"orchestrator claimed={report.claimed}")


if __name__ == "__main__":
    main()


__all__ = ["OrchestratorRunReport", "main", "run_forever", "run_once"]
