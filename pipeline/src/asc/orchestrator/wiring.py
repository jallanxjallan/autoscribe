"""Concrete wiring for the orchestrator service."""

from __future__ import annotations

from typing import Any

from asc.core.timestamp import timestamp

from .service import OrchestratorService


class ModuleQueue:
    """Adapter for state queue modules exposing claim()/insert()."""

    def __init__(self, module: Any) -> None:
        self.module = module

    def claim(self) -> Any | None:
        return self.module.claim()

    def insert(self, cursor_key: str) -> int:
        return int(self.module.insert(cursor_key))


class RedisStore:
    def load_cursor(self, key: str) -> Any:
        from asc.models.runtime.cursor import RuntimeCursor

        return RuntimeCursor.load(key)

    def load_plan(self, key: str) -> Any:
        from asc.models.control.plan import PlanRecord

        return PlanRecord.load(key)

    def save_cursor_with_job(self, cursor: Any, job_key: str) -> Any:
        updated = cursor.model_copy(
            update={
                "current_job_key": str(job_key),
                "updated_at": timestamp(),
            }
        )
        updated.save()
        return updated

    def clear_cursor_job(self, cursor: Any) -> Any:
        updated = cursor.model_copy(
            update={
                "current_job_key": "",
                "updated_at": timestamp(),
            }
        )
        updated.save()
        return updated

    def save_job(self, job: Any) -> str:
        return str(job.save())

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
