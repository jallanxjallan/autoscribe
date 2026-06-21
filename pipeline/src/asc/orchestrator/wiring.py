"""Concrete wiring for the orchestrator service."""

from __future__ import annotations

from typing import Any

from .context import OrchestratorContext
from .service import OrchestratorService


class QueueAdapter:
    """Adapter for the orchestrator's own state queue module."""

    def __init__(self, module: Any) -> None:
        self.module = module

    def claim(
        self,
        *,
        timeout: int | None = None,
        empty_limit: int | None = None,
        wait: bool = False,
    ) -> Any | None:
        if wait:
            daemon_claim = getattr(self.module, "daemon_claim", None)
            if callable(daemon_claim):
                return daemon_claim(timeout=timeout, empty_limit=empty_limit)

            block_claim = getattr(self.module, "block_claim", None)
            if callable(block_claim):
                return block_claim(timeout=timeout)

        drain_claim = getattr(self.module, "daemon_drain_claim", None)
        if callable(drain_claim):
            return drain_claim()

        return self.module.claim()


class InboxAdapter:
    """Adapter for worker/scrivener public inbox modules."""

    def __init__(self, module: Any) -> None:
        self.module = module

    def post(self, key: str) -> str:
        return str(self.module.post(key))


class RedisStore:
    def load_cursor_for_identity(self, identity: str) -> Any:
        from asc.models.process.cursor import Cursor

        return Cursor.load(f"cursor:{identity}:index")

    def load_plan(self, key: str) -> Any:
        from asc.models.control.plan import Plan

        return Plan.load(key)

    def result_key_for_step(self, *, identity: str, step_number: int) -> str:
        from asc.state.results import ResultsIndex

        return str(ResultsIndex(f"results:{identity}:index").get(int(step_number)))

    def input_key_for_step(self, *, identity: str, step_number: int) -> str:
        from asc.state.results import ResultsIndex

        return str(ResultsIndex(f"results:{identity}:index").input_key_for_step(int(step_number)))

    def load_failure(self, key: str) -> Any:
        from asc.models.process.failure import Failure

        return Failure.load(key)

    def save_task(self, task: Any) -> str:
        saved = task.save()
        return str(saved or task.key)


def build_service() -> OrchestratorService:
    from asc.orchestrator import inbox as orchestrator_inbox  # noqa: F401 - documents public contract
    from asc.scrivener import inbox as scrivener_inbox
    from asc.state import orchestrator_queue
    from asc.worker import inbox as worker_inbox

    return OrchestratorService(
        queue=QueueAdapter(orchestrator_queue),
        context=OrchestratorContext(
            store=RedisStore(),
            worker_inbox=InboxAdapter(worker_inbox),
            scrivener_inbox=InboxAdapter(scrivener_inbox),
        ),
    )


__all__ = ["InboxAdapter", "QueueAdapter", "RedisStore", "build_service"]
