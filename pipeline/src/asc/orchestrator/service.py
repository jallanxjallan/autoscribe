"""Single-pass orchestrator service.

Queues carry Redis keys, not hydrated model state.

* Enqueue may place one fresh cursor key on the orchestrator queue.
* The orchestrator activates that cursor in ``state:runtime:active``.
* After activation, every queue handoff is a job key.
* Workers and scrivener return completed job keys to the orchestrator.

That removes the fragile ``cursor.current_job`` contract. The cursor remains the
stable call context and active-index member; the job key itself is the handoff token for daemon work.
"""

from __future__ import annotations

from typing import Any, Protocol

from asc.models.runtime.job import LedgerJobRecord, WorkerJobRecord

from .tasks import (
    RouteDecision,
    cursor_key_for,
    load_job,
    make_ledger_call_job,
    make_ledger_result_job,
    make_ledger_step_job,
    make_worker_job,
    plan_step_count,
    runtime_job_key_for,
    assert_job_key_for_queue,
)


class StoreLike(Protocol):
    def load_cursor(self, key: str) -> Any: ...
    def load_plan(self, key: str) -> Any: ...
    def save_job(self, job: Any) -> None: ...
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

        cursor, completed_job = self._load_context(claimed_key)
        cursor_key = cursor_key_for(cursor)
        self.store.touch_active_cursor(cursor_key)

        decision = self.route(cursor=cursor, completed_job=completed_job)
        if decision.job is None:
            self.store.bump_terminal_cursor(cursor_key)
            return True

        # Persist the job, but never trust save() as the queue token.
        # The queue contract is explicit: downstream queues receive job keys,
        # while only the orchestrator queue may receive a fresh cursor key.
        self.store.save_job(decision.job)
        job_key = runtime_job_key_for(decision.job)
        assert_job_key_for_queue(queue_name=decision.queue_name, job_key=job_key)

        if decision.queue_name == "worker":
            self.worker_queue.insert(job_key)
        elif decision.queue_name == "scrivener":
            self.scrivener_queue.insert(job_key)
        elif decision.queue_name == "orchestrator":
            self.orchestrator_queue.insert(job_key)
        else:
            raise ValueError(f"unknown queue route: {decision.queue_name!r}")

        return True

    def _load_context(self, claimed_key: str) -> tuple[Any, WorkerJobRecord | LedgerJobRecord | None]:
        """Load cursor plus optional completed job from an orchestrator queue key."""

        if claimed_key.endswith(":cursor"):
            return self.store.load_cursor(claimed_key), None

        completed_job = load_job(claimed_key)
        cursor_key = str(getattr(completed_job, "cursor_key", "")).strip()
        if not cursor_key:
            raise ValueError(f"completed job has no cursor_key: {claimed_key}")
        return self.store.load_cursor(cursor_key), completed_job

    def route(
        self,
        *,
        cursor: Any,
        completed_job: WorkerJobRecord | LedgerJobRecord | None,
    ) -> RouteDecision:
        if completed_job is None:
            return RouteDecision(
                queue_name="scrivener",
                job=make_ledger_call_job(cursor),
                reason="new call needs call ledger row",
            )

        if isinstance(completed_job, WorkerJobRecord):
            return RouteDecision(
                queue_name="scrivener",
                job=make_ledger_step_job(cursor=cursor, worker_job=completed_job),
                reason="worker job completed; write step ledger row",
            )

        if isinstance(completed_job, LedgerJobRecord):
            return self._route_after_ledger_job(cursor, completed_job)

        raise TypeError(f"unknown completed job type: {type(completed_job).__name__}")

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
