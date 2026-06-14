from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast

from asc.models.control.plan import PlanRecord
from asc.models.runtime.call import CallRecord
from asc.models.runtime.cursor import RuntimeCursor
from asc.workers.engines import load_engine_call
from asc.workers.outcome import submit_outcome


class EngineOutcomeRecord(Protocol):
    """Record returned by an engine for the current step.

    Engines own the result/failure distinction. A successful engine should return
    a StepResult-style record; a caught engine failure should return a
    StepFailure-style record. The worker only persists the returned record at the
    cursor-supplied output key and then hands the cursor back to the
    orchestrator.
    """

    def save_as(self, key: str) -> None: ...


@dataclass(frozen=True, slots=True)
class WorkerResult:
    processed: int
    cursor_key: str
    output_key: str


class WorkerExecutor:
    def execute(self, cursor_key: str) -> WorkerResult:
        cursor = RuntimeCursor.load(cursor_key)
        plan = PlanRecord.load(cursor.plan_key)
        input_record = CallRecord.load(cursor.input_key)

        step_number = cursor.current_step
        engine = plan.step_engine(step_number)
        args = plan.step_args(step_number)

        engine_call = load_engine_call(engine, args=args)
        outcome = cast(EngineOutcomeRecord, engine_call(input_record.content))
        outcome.save_as(cursor.output_key)

        submit_outcome(cursor_key)

        return WorkerResult(
            processed=1,
            cursor_key=cursor_key,
            output_key=cursor.output_key,
        )


__all__ = ["EngineOutcomeRecord", "WorkerExecutor", "WorkerResult"]
