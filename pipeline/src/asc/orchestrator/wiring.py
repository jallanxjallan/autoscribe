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
        """Load a cursor without interpreting response-index keys as models."""

        text = str(key).strip()
        if not text:
            raise ValueError("empty cursor key")

        # Prefer the concrete cursor model.  Generic loaders have historically
        # guessed from the final key segment, which turns ``cursor:<id>:index``
        # into an attempted ``Index`` model load.
        import_errors: list[str] = []
        for module_name, class_names in (
            ("asc.models.process.cursor", ("Cursor", "RuntimeCursor")),
            ("asc.models.runtime.cursor", ("Cursor", "RuntimeCursor")),
        ):
            try:
                module = __import__(module_name, fromlist=list(class_names))
            except Exception as exc:  # pragma: no cover - migration bridge
                import_errors.append(f"{module_name}: {exc}")
                continue

            for class_name in class_names:
                model = getattr(module, class_name, None)
                if model is None:
                    continue
                load = getattr(model, "load", None)
                if callable(load):
                    try:
                        return load(text)
                    except TypeError:
                        pass
                load_key = getattr(model, "load_key", None)
                if callable(load_key):
                    return load_key(text)

        try:
            from asc.models.process.loader import load_key

            return load_key(text)
        except Exception as exc:
            details = "; ".join(import_errors)
            raise LookupError(f"cannot load cursor for key {text!r}; {details}; generic loader: {exc}") from exc

    def load_plan(self, key: str) -> Any:
        from asc.models.control.plan import Plan

        return Plan.load(key)

    def save_task(self, task: Any) -> None:
        task.save()
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
