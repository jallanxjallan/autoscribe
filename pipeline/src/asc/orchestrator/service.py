"""Single-pass orchestrator service.

The orchestrator owns job assignment. Queues move cursor keys only. The cursor
stores the currently assigned job key; when the cursor returns to the
orchestrator, that job is treated as completed and the next job is assigned.
"""

from __future__ import annotations

from typing import Any, Protocol

from asc.core.timestamp import timestamp
from asc.models.runtime.job import LedgerJobRecord, WorkerJobRecord

from .jobs import (
    RouteDecision,
    current_job_key,
    cursor_key_for,
    load_job,
    make_ledger_call_job,
    make_ledger_result_job,
    make_ledger_step_job,
    make_worker_job,
    plan_step_count,
)


class StoreLike(Protocol):
    def load_cursor(self, key: str) -> Any: ...
    def load_plan(self, key: str) -> Any: ...
    def save_cursor_with_job(self, cursor: Any, job_key: str) -> Any: ...
    def clear_cursor_job(self, cursor: Any) -> Any: ...
    def save_job(self, job: Any) -> str: ...
    def touch_active_cursor(self, cursor_key: str) -> None: ...
    def bump_terminal_cursor(self, cursor_key: str) -> None: ...


class QueueLike(Protocol):
    def claim(self) -> Any | None: ...
    def insert(self, cursor_key: str) -> int: ...


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

    def run_once(self) -> bool:
        claimed = self.orchestrator_queue.claim()
        if claimed is None:
            return False

        cursor_key = str(getattr(claimed, "key", claimed))
        cursor = self.store.load_cursor(cursor_key)
        self.store.touch_active_cursor(cursor_key)

        decision = self.route(cursor)
        if decision.job is None:
            self.store.clear_cursor_job(cursor)
            self.store.bump_terminal_cursor(cursor_key)
            return True

        job_key = self.store.save_job(decision.job)
        cursor = self.store.save_cursor_with_job(cursor, job_key)
        next_cursor_key = cursor_key_for(cursor)

        if decision.queue_name == "worker":
            self.worker_queue.insert(next_cursor_key)
        elif decision.queue_name == "scrivener":
            self.scrivener_queue.insert(next_cursor_key)
        elif decision.queue_name == "orchestrator":
            self.orchestrator_queue.insert(next_cursor_key)
        else:
            raise ValueError(f"unknown queue route: {decision.queue_name!r}")

        return True

    def route(self, cursor: Any) -> RouteDecision:
        job_key = current_job_key(cursor)

        if not job_key:
            return RouteDecision(
                queue_name="scrivener",
                job=make_ledger_call_job(cursor),
                reason="new call needs call ledger row",
            )

        completed_job = load_job(job_key)

        if isinstance(completed_job, WorkerJobRecord):
            return RouteDecision(
                queue_name="scrivener",
                job=make_ledger_step_job(cursor=cursor, worker_job=completed_job),
                reason="worker job completed; write step ledger row",
            )

        if isinstance(completed_job, LedgerJobRecord):
            return self._route_after_ledger_job(cursor, completed_job)

        raise TypeError(f"unknown current job type: {type(completed_job).__name__}")

    def _route_after_ledger_job(self, cursor: Any, job: LedgerJobRecord) -> RouteDecision:
        if job.action == "write_result":
            return RouteDecision(
                queue_name=None,
                job=None,
                reason="terminal result already written",
            )

        plan = self.store.load_plan(cursor.plan_key)
        total_steps = plan_step_count(plan)

        if job.action == "write_call":
            if total_steps < 1:
                return RouteDecision(
                    queue_name="scrivener",
                    job=make_ledger_result_job(cursor=cursor, previous_job=job),
                    reason="plan has no worker steps; write terminal result",
                )
            return RouteDecision(
                queue_name="worker",
                job=make_worker_job(cursor=cursor, plan=plan, step_number=1),
                reason="call ledger row written; execute step 1",
            )

        if job.action == "write_step":
            next_step = int(job.step_number) + 1
            if next_step > total_steps:
                return RouteDecision(
                    queue_name="scrivener",
                    job=make_ledger_result_job(cursor=cursor, previous_job=job),
                    reason="terminal step ledger row written; write result row",
                )
            return RouteDecision(
                queue_name="worker",
                job=make_worker_job(
                    cursor=cursor,
                    plan=plan,
                    step_number=next_step,
                    input_key=job.input_key,
                ),
                reason=f"step {job.step_number} ledger row written; execute step {next_step}",
            )

        raise ValueError(f"unknown ledger job action: {job.action!r}")
