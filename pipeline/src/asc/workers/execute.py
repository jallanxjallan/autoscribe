from __future__ import annotations

from dataclasses import dataclass

from asc.models.control.plan import PlanRecord
from asc.models.runtime.cursor import RuntimeCursor
from asc.runtime.response_index import (
    record_response_output,
    response_input_key,
    response_output_key,
)
from asc.workers.engines import load_engine_call
from asc.workers.outcome import submit_outcome
from asc.workers.runtime_io import load_runtime_content


@dataclass(frozen=True, slots=True)
class WorkerResult:
    processed: int
    cursor_key: str
    output_key: str


class WorkerExecutor:
    def execute(self, cursor_key: str) -> WorkerResult:
        cursor = RuntimeCursor.load(cursor_key)
        plan = PlanRecord.load(cursor.plan_key)

        step_number = int(cursor.current_step)
        input_key = response_input_key(cursor.response_index_key, step_number)
        input_content = load_runtime_content(input_key)

        engine = plan.step_engine(step_number)
        args = plan.step_args(step_number)

        engine_call = load_engine_call(engine, args=args)
        outcome = engine_call(input_content)

        output_key = response_output_key(cursor.identity, step_number)

        # TODO:
        # Development mode fails fast so contract violations are immediately
        # visible. In production the worker should never die because an engine
        # returned an unexpected object. Instead, catch the exception, log it,
        # persist a StepFailure record, return the cursor to the orchestrator queue,
        # and allow the orchestrator to decide whether to retry, fail, or
        # escalate the call.
        try:
            outcome.save(output_key)
        except AttributeError as exc:
            raise TypeError(
                f"Engine {engine!r} returned {type(outcome).__name__}, "
                "not a RedisModel-compatible StepResult or StepFailure"
            ) from exc

        record_response_output(cursor.response_index_key, step_number, output_key)
        submit_outcome(cursor_key)

        return WorkerResult(
            processed=1,
            cursor_key=cursor_key,
            output_key=output_key,
        )


__all__ = ["WorkerExecutor", "WorkerResult"]
