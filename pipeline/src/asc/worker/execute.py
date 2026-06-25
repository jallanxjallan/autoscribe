"""Worker execution boundary.

The worker queue carries a WorkerTask key. The task is the custody/envelope
record. The executable runtime instruction is the Step stored at
WorkerTask.step_key. The runtime input is the already-selected data record at
WorkerTask.data_key.

By the time the worker sees a Step, plan step definitions have already been
flattened into top-level fields. Do not parse args_json or reload/unpack the
Plan here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from asc.models.process.result import Failure, Result
from asc.models.process.step import Step
from asc.models.process.task import Outcome, WorkerTask
from asc.worker.engines import load_engine_run
from asc.worker.runtime_io import load_runtime_content


@dataclass(frozen=True, slots=True)
class WorkerResult:
    processed: int
    task_key: str
    output_key: str
    outcome_key: str


class WorkerExecutor:
    def execute(self, task: WorkerTask, task_key: str) -> WorkerResult:
        step: Step | None = None

        try:
            step = Step.load(task.step_key)
            input_content = load_runtime_content(task.data_key)
            engine_run = load_engine_run(step.engine, args=_step_args(step))
            output = engine_run(input_content)
            result = Result.from_worker_output(output, task=task, step=step, task_key=task_key)
        except Exception as exc:
            result = Failure.internal(
                task_key=task_key,
                task=task,
                exc=exc,
                boundary="worker.execute",
                step_key=task.step_key,
                data_key=task.data_key,
            )
            if step is not None:
                result = result.with_worker_context(task=task, step=step, task_key=task_key)

        output_key = result.save()
        outcome_key = _save_outcome(
            task=task,
            task_key=task_key,
            output_key=output_key,
            result=result,
            step=step,
        )

        return WorkerResult(
            processed=1,
            task_key=task_key,
            output_key=output_key,
            outcome_key=outcome_key,
        )


def _save_outcome(
    *,
    task: WorkerTask,
    task_key: str,
    output_key: str,
    result: Result | Failure,
    step: Step | None,
) -> str:
    status = "failure" if isinstance(result, Failure) else "success"
    payload = {
        **task.model_dump(mode="json"),
        "identity": task.identity,
        "task_identity": task.identity,
        "task_key": task_key,
        "package": "worker",
        "action": task.action,
        "status": status,
        "result": status,
        "output_key": output_key,
        "step_number": _step_number(step=step),
        "result_key": "" if status == "failure" else output_key,
        "failure_key": output_key if status == "failure" else "",
    }

    outcome = Outcome.model_validate(_payload_for_model(Outcome, payload))
    return outcome.save()


def _step_number(*, step: Step | None) -> str:
    if step is None:
        raise ValueError("worker outcome requires loaded step with mandatory step_number")

    return str(step.step_number)


def _payload_for_model(model: type[Any], payload: dict[str, Any]) -> dict[str, Any]:
    config = getattr(model, "model_config", {})
    allows_extra = isinstance(config, dict) and config.get("extra") == "allow"
    if allows_extra:
        return payload

    fields = getattr(model, "model_fields", None)
    if not fields:
        return payload

    return {key: value for key, value in payload.items() if key in fields}


def _step_args(step: Step) -> dict[str, Any]:
    return {
        name: value
        for name, value in step.model_dump(mode="python").items()
        if value not in (None, "")
    }


__all__ = ["WorkerExecutor", "WorkerResult"]
