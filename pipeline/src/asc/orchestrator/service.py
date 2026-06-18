"""Single-pass orchestrator service.

Queues carry Redis keys, not hydrated model state.

Progress lives in the response index, not in mutable cursor fields.  Before a
worker task is queued, the orchestrator claims the response-index step slot with
a short-lived in-process marker.  The worker outcome must later replace that
marker with a result or failure key.
"""

from __future__ import annotations

from typing import Any, Protocol


from asc.models.process.task import ScrivenerTask, WorkerTask


from .outcomes import ScrivenerOutcome, WorkerOutcome, outcome_from_key
from .response_manager import (
    input_key_for_step,
    mark_step_in_flight,
    record_step_output,
)

from .tasks import (
    RouteDecision,
    assert_task_key_for_queue,
    cursor_key_for,
    is_cursor_key,
    make_scrivener_call_task,
    make_scrivener_result_task,
    make_scrivener_step_task,
    make_worker_task,
    plan_step_count,
    runtime_task_key_for,
    task_number_for,
)


class StoreLike(Protocol):
    def load_cursor(self, key: str) -> Any: ...
    def load_plan(self, key: str) -> Any: ...
    def save_task(self, task: Any) -> None: ...
    def touch_active_cursor(self, cursor_key: str) -> None: ...
    def bump_terminal_cursor(self, cursor_key: str) -> None: ...


class QueueLike(Protocol):
    def claim(
        self,
        *,
        timeout: int | None = None,
        empty_limit: int | None = None,
        wait: bool = False,
    ) -> Any | None: ...
    def insert(self, key: str) -> int: ...


class OrchestratorService:
    def __init__(
        self,
        *,
        store: StoreLike,
        orchestrator_queue: QueueLike,
        worker_queue: QueueLike,
        scrivener_queue: QueueLike,
    ) -> None:
        self.store = store
        self.orchestrator_queue = orchestrator_queue
        self.worker_queue = worker_queue
        self.scrivener_queue = scrivener_queue

    def run_once(
        self,
        *,
        timeout: int | None = None,
        empty_limit: int | None = None,
        wait: bool = False,
    ) -> bool:
        claimed = self.orchestrator_queue.claim(
            timeout=timeout,
            empty_limit=empty_limit,
            wait=wait,
        )
        if claimed is None:
            return False

        claimed_key = str(getattr(claimed, "key", claimed)).strip()
        if not claimed_key:
            raise ValueError("orchestrator claimed an empty queue key")

        cursor, outcome = self._load_context(claimed_key)
        cursor_key = cursor_key_for(cursor)
        self.store.touch_active_cursor(cursor_key)

        decision = self.route(cursor=cursor, outcome=outcome)
        if decision.task is None:
            self.store.bump_terminal_cursor(cursor_key)
            return True

        # Persist the task, but never trust save() as the queue token.
        # The queue contract is explicit: downstream queues receive task keys,
        # while only the orchestrator queue may receive a fresh cursor key.
        self.store.save_task(decision.task)
        task_key = runtime_task_key_for(decision.task)
        assert_task_key_for_queue(queue_name=decision.queue_name, task_key=task_key)

        if decision.queue_name == "worker":
            self._claim_worker_step(cursor=cursor, worker_task=decision.task)
            self.worker_queue.insert(task_key)
        elif decision.queue_name == "scrivener":
            self.scrivener_queue.insert(task_key)
        elif decision.queue_name == "orchestrator":
            self.orchestrator_queue.insert(task_key)
        else:
            raise ValueError(f"unknown queue route: {decision.queue_name!r}")

        return True

    def _claim_worker_step(self, *, cursor: Any, worker_task: WorkerTask) -> None:
        """Write an in-process marker into the response index before enqueue."""

        step_number = task_number_for(worker_task)
        mark_step_in_flight(
            cursor=cursor,
            step_number=step_number,
            task_key=runtime_task_key_for(worker_task),
            cursor_key=cursor_key_for(cursor),
        )

    def _record_worker_output(self, *, cursor: Any, worker_task: WorkerTask) -> None:
        """Replace an in-process marker with the worker-produced output key."""

        produced_key = str(getattr(worker_task, "output_key", "")).strip()
        if not produced_key:
            raise ValueError("worker task has no output_key to record in response index")

        record_step_output(
            cursor=cursor,
            step_number=task_number_for(worker_task),
            produced_key=produced_key,
        )

    def _load_context(self, claimed_key: str) -> tuple[Any, WorkerOutcome | ScrivenerOutcome | None]:
        """Load cursor plus optional completed task outcome from an orchestrator queue key."""

        if is_cursor_key(claimed_key):
            return self.store.load_cursor(claimed_key), None

        outcome = outcome_from_key(claimed_key)
        return self.store.load_cursor(outcome.cursor_key), outcome

    def route(
        self,
        *,
        cursor: Any,
        outcome: WorkerOutcome | ScrivenerOutcome | None,
    ) -> RouteDecision:
        if outcome is None:
            return RouteDecision(
                queue_name="scrivener",
                task=make_scrivener_call_task(cursor),
                reason="new call needs call ledger row",
            )

        if isinstance(outcome, WorkerOutcome):
            self._record_worker_output(cursor=cursor, worker_task=outcome.task)
            return RouteDecision(
                queue_name="scrivener",
                task=make_scrivener_step_task(cursor=cursor, worker_task=outcome.task),
                reason="worker task completed; write step ledger row",
            )

        if isinstance(outcome, ScrivenerOutcome):
            return self._route_after_scrivener_task(cursor, outcome.task)

        raise TypeError(f"unknown outcome type: {type(outcome).__name__}")

    def _route_after_scrivener_task(self, cursor: Any, task: ScrivenerTask) -> RouteDecision:
        if task.action in {"call_completed", "write_export", "export_written"}:
            return RouteDecision(
                queue_name=None,
                task=None,
                reason="terminal result already written",
            )

        plan = self.store.load_plan(cursor.plan_key)
        total_steps = plan_step_count(plan)

        if task.action == "write_call":
            if total_steps < 1:
                return RouteDecision(
                    queue_name="scrivener",
                    task=make_scrivener_result_task(cursor=cursor, previous_task=task),
                    reason="plan has no worker steps; write terminal result",
                )
            return RouteDecision(
                queue_name="worker",
                task=make_worker_task(
                    cursor=cursor,
                    plan=plan,
                    step_number=1,
                    input_key=input_key_for_step(cursor, 1),
                ),
                reason="call ledger row written; execute step 1",
            )

        if task.action == "write_step":
            task_number = task_number_for(task)
            next_step = task_number + 1
            if next_step > total_steps:
                return RouteDecision(
                    queue_name="scrivener",
                    task=make_scrivener_result_task(cursor=cursor, previous_task=task),
                    reason="terminal step ledger row written; write result row",
                )
            return RouteDecision(
                queue_name="worker",
                task=make_worker_task(
                    cursor=cursor,
                    plan=plan,
                    step_number=next_step,
                    input_key=input_key_for_step(cursor, next_step),
                ),
                reason=f"task {task_number} ledger row written; execute task {next_step}",
            )

        raise ValueError(f"unknown scrivener task action: {task.action!r}")


__all__ = ["OrchestratorService", "QueueLike", "StoreLike"]
