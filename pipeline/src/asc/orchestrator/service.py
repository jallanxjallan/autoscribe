"""Single-pass orchestrator service.

The queue carries Redis keys only.  The orchestrator owns this queue and routing
logic.  It does not own the cursor index, active index, results index, ledger,
worker queue, or scrivener queue.
"""

from __future__ import annotations

from typing import Any, Protocol

from .context import OrchestratorContext
from .contracts import ORCHESTRATOR_POST_KINDS
from .errors import OrchestratorContractError
from .handlers import HANDLERS
from .keys import RuntimeKey


class Queue(Protocol):
    def claim(
        self,
        *,
        timeout: int | None = None,
        empty_limit: int | None = None,
        wait: bool = False,
    ) -> Any | None: ...


class OrchestratorService:
    def __init__(self, *, queue: Queue, context: OrchestratorContext) -> None:
        self.queue = queue
        self.context = context

    def run_once(
        self,
        *,
        timeout: int | None = None,
        empty_limit: int | None = None,
        wait: bool = False,
    ) -> bool:
        claimed = self.queue.claim(timeout=timeout, empty_limit=empty_limit, wait=wait)
        if claimed is None:
            return False

        posted = RuntimeKey.parse(str(getattr(claimed, "key", claimed)).strip())
        if posted.kind not in ORCHESTRATOR_POST_KINDS:
            expected = ", ".join(sorted(ORCHESTRATOR_POST_KINDS))
            raise OrchestratorContractError(
                f"orchestrator claimed unsupported kind {posted.kind!r}; expected {expected}: {posted.raw}"
            )

        HANDLERS[posted.kind](posted, self.context)
        return True


__all__ = ["OrchestratorService", "Queue"]
