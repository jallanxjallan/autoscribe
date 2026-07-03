"""Orchestrator daemon entrypoint using the active-call zset.

Run once from the command line:
    python -m asc.orchestrator.daemon

Run forever from imported code:
    from asc.orchestrator.daemon import run_forever
    run_forever()
"""

from dataclasses import dataclass
import time

from asc.orchestrator.active import (
    active_call_window,
    bump_active_call,
    defer_active_call,
    remove_active_call,
    seconds_until_next_visible,
    ORCHESTRATOR_IDLE_SLEEP_SECONDS,
)
from asc.orchestrator.handle import handle
from asc.redis.key import RedisKey
from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, configure_logging


@dataclass(frozen=True, slots=True)
class OrchestratorRunReport:
    claimed: bool
    call_key: str | None = None
    active: bool | None = None
    waiting: bool | None = None

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

    now = time.time()
    window = active_call_window()
    visible = [call for call in window if call.score <= now]

    if not visible:
        if wait:
            delay = seconds_until_next_visible(calls=window)
            time.sleep(delay if delay is not None else ORCHESTRATOR_IDLE_SLEEP_SECONDS)
        return OrchestratorRunReport(claimed=False)

    waiting = False

    for call in visible:
        result = handle(call.key)

        if not result.active:
            remove_active_call(call.key)
            return OrchestratorRunReport(
                claimed=True,
                call_key=call.key,
                active=False,
                waiting=False,
            )

        if result.waiting:
            waiting = True
            defer_active_call(call.key)
            continue

        bump_active_call(call.key)
        return OrchestratorRunReport(
            claimed=True,
            call_key=call.key,
            active=True,
            waiting=False,
        )

    if wait and waiting:
        time.sleep(ORCHESTRATOR_IDLE_SLEEP_SECONDS)

    return OrchestratorRunReport(claimed=False, waiting=waiting)


def run_forever(
    *,
    timeout: int = DEFAULT_CLAIM_TIMEOUT_SECONDS,
    empty_limit: int | None = None,
) -> None:
    """Run the orchestrator loop forever.

    The orchestrator polls the active-call zset rather than blocking on a Redis
    inbox.  It must therefore not use the shared idle-shutdown daemon runner:
    a temporarily waiting worker/scrivener task is normal pipeline state, not a
    reason for the orchestrator process to exit.

    ``timeout`` and ``empty_limit`` are accepted for API compatibility with the
    managed run surface. They are intentionally ignored here.
    """

    configure_logging()
    while True:
        run_once(wait=True)


def main() -> None:
    """Run one orchestrator cycle from the command line."""

    configure_logging()
    report = run_once()
    print(
        f"orchestrator claimed={report.claimed} "
        f"call_key={report.call_key} active={report.active} "
        f"waiting={report.waiting} kind={report.kind}"
    )


if __name__ == "__main__":
    main()


__all__ = ["OrchestratorRunReport", "main", "run_forever", "run_once"]
