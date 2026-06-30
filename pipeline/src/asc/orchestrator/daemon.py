"""Orchestrator daemon entrypoint using the active-call zset.

Run once from the command line:
    python -m asc.orchestrator.daemon

Run forever from imported code:
    from asc.orchestrator.daemon import run_forever
    run_forever()
"""

from dataclasses import dataclass

from asc.orchestrator.active import bump_active_call, oldest_active_call, remove_active_call
from asc.orchestrator.handle import handle
from asc.redis.key import RedisKey
from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, configure_logging, run_daemon


@dataclass(frozen=True, slots=True)
class OrchestratorRunReport:
    claimed: bool
    call_key: str | None = None
    active: bool | None = None

    @property
    def post_key(self) -> str | None:
        return self.call_key

    @property
    def kind(self) -> str | None:
        if self.call_key is None:
            return None
        return RedisKey(self.call_key).kind


def run_once(
    *,
    timeout: int | None = None,
    empty_limit: int | None = None,
    wait: bool = False,
) -> OrchestratorRunReport:
    """Inspect and advance one active call.

    ``timeout``, ``empty_limit``, and ``wait`` are accepted for compatibility
    with the shared daemon runner. Active calls are polled from the zset rather
    than claimed from a blocking inbox.
    """

    call_key = oldest_active_call()
    if call_key is None:
        return OrchestratorRunReport(claimed=False)

    active = handle(call_key)
    if active:
        bump_active_call(call_key)
    else:
        remove_active_call(call_key)

    return OrchestratorRunReport(claimed=True, call_key=call_key, active=active)


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
    report = run_once()
    print(
        f"orchestrator claimed={report.claimed} "
        f"call_key={report.call_key} active={report.active} kind={report.kind}"
    )


if __name__ == "__main__":
    main()


__all__ = ["OrchestratorRunReport", "main", "run_forever", "run_once"]
