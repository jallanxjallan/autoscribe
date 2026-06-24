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
from asc.models.process.task import WorkerTask
from asc.worker.engines import load_engine_run
from asc.worker.runtime_io import load_runtime_content


@dataclass(frozen=True, slots=True)
class WorkerResult:
    processed: int
    task_key: str
    output_key: str


class WorkerExecutor:
    def execute(self, task: WorkerTask, task_key: str) -> WorkerResult:
        step = Step.load(task.step_key)

        try:
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

        output_key = result.save()
        return WorkerResult(
            processed=1,
            task_key=task_key,
            output_key=output_key,
        )


def _step_args(step: Step) -> dict[str, Any]:
    excluded = {
        "identity",
        "suffix",
        "call_key",
        "number",
        "step_number",
        "engine",
        "executor",
        "action",
        "instructions_json",
        "args_json",
        "ttl_seconds",
        "created_at",
        "updated_at",
    }

    return {
        name: value
        for name, value in step.model_dump(mode="python").items()
        if name not in excluded and value not in (None, "")
    }


__all__ = ["WorkerExecutor", "WorkerResult"]
