from __future__ import annotations

from dataclasses import dataclass

from asc.models.control.plan import PlanRecord
from asc.models.runtime.call import CallRecord
from asc.models.runtime.cursor import RuntimeCursor
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
        plan = PlanRecord.load(cursor.plan_key)
        input_record = CallRecord.load(cursor.input_key)

        step_number = cursor.current_step
        engine = plan.step_engine(step_number)
        args = plan.step_args(step_number)

        engine_call = load_engine_call(engine, args=args)
        outcome = engine_call(input_record.content)

        # TODO:
        # Development mode fails fast so contract violations are immediately
        # visible. In production the worker should never die because an engine
        # returned an unexpected object. Instead, catch the exception, log it,
        # persist a StepFailure record, submit the cursor to the outcome queue,
        # and allow the orchestrator to decide whether to retry, fail, or
        # escalate the call.
        try:
            outcome.save(cursor.output_key)
        except AttributeError as exc:
            raise TypeError(
                f"Engine {engine!r} returned {type(outcome).__name__}, "
                "not a RedisModel-compatible StepResult or StepFailure"
            ) from exc

        try:
            outcome.save(cursor.output_key)
        except AttributeError as exc:
            raise TypeError(
                f"Engine {engine!r} returned {type(outcome).__name__}, "
                "not a RedisModel-compatible StepResult or StepFailure"
            ) from exc

        submit_outcome(cursor_key)

        return WorkerResult(
            processed=1,
            cursor_key=cursor_key,
            output_key=cursor.output_key,
        )


__all__ = ["WorkerExecutor", "WorkerResult"]