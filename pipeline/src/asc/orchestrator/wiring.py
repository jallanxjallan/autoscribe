"""Concrete wiring for the orchestrator service."""

from __future__ import annotations

from typing import Any

from .service import OrchestratorService


class ModuleQueue:
    """Adapter for state queue modules exposing claim()/insert()."""

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

            if timeout is not None:
                block_claim = getattr(self.module, "block_claim", None)
                if callable(block_claim):
                    return block_claim(timeout=timeout)

        drain_claim = getattr(self.module, "daemon_drain_claim", None)
        if callable(drain_claim):
            return drain_claim()

        return self.module.claim()

    def insert(self, cursor_key: str) -> int:
        return int(self.module.insert(cursor_key))


class RedisStore:
    def load_cursor(self, key: str) -> Any:
        from asc.models.runtime.loader import load_key

        return load_key(key)

    def load_plan(self, key: str) -> Any:
        from asc.models.control.plan import Plan

        return Plan.load(key)

    def save_job(self, job: Any) -> None:
        job.save()
        return None

    def touch_active_cursor(self, cursor_key: str) -> None:
        try:
            from asc.state import orchestrator_index
        except Exception:
            return
        orchestrator_index.touch(cursor_key)

    def bump_terminal_cursor(self, cursor_key: str) -> None:
        try:
            from asc.state import orchestrator_index
        except Exception:
            return
        orchestrator_index.reschedule(
            cursor_key,
            delay_seconds=60.0 * 60.0 * 24.0 * 365.0 * 10.0,
        )


def build_service() -> OrchestratorService:
    from asc.state import orchestrator_queue, scrivener_queue, worker_queue

    return OrchestratorService(
        store=RedisStore(),
        orchestrator_queue=ModuleQueue(orchestrator_queue),
        worker_queue=ModuleQueue(worker_queue),
        scrivener_queue=ModuleQueue(scrivener_queue),
    )
