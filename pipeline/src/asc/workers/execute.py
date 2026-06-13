from __future__ import annotations

from dataclasses import dataclass

from asc.models.control.step import PlanStepRecord
from asc.models.runtime.call import CallRecord
from asc.models.runtime.cursor import RuntimeCursor
from asc.models.runtime.result import StepResultRecord
from asc.workers.engines import load_engine_call
from asc.workers.outcome import submit_outcome


@dataclass(frozen=True, slots=True)
class WorkerResult:
    processed: int
    cursor_key: str
    output_key: str


class WorkerExecutor:
    def execute(self, cursor_key: str) -> WorkerResult:
        cursor = RuntimeCursor.load(cursor_key)
        step = PlanStepRecord.load(cursor.step_key)
        input_record = CallRecord.load(cursor.input_key)

        engine_call = load_engine_call(step.engine, args=step.definition)
        result_args = engine_call(input_record.record_content)

        result = StepResultRecord(**result_args)
        result.save_as(cursor.output_key)

        submit_outcome(cursor_key)

        return WorkerResult(
            processed=1,
            cursor_key=cursor_key,
            output_key=cursor.output_key,
        )


__all__ = ["WorkerExecutor", "WorkerResult"]
