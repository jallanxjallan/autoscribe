import json
from dataclasses import dataclass
from typing import Any

from asc.redis.key import RedisKey
from asc.workers.engines import load_engine_call
from asc.workers.outcome import post_worker_outcome
from asc.workers.runtime_io import load_runtime_content


@dataclass(frozen=True, slots=True)
class WorkerResult:
    processed: int
    cursor_key: str
    task_key: str
    output_key: str


class WorkerExecutor:
    def execute(self, task_key: str) -> WorkerResult:
        task_key = str(task_key).strip()
        if not task_key:
            raise ValueError("worker claimed an empty task key")

        task = _load_task(task_key)
        cursor_key = str(_required_task_value(task, "cursor_key", task_key))
        step_number = int(_required_task_value(task, "step_number", task_key))
        input_key = str(_required_task_value(task, "input_key", task_key))
        output_key = str(_required_task_value(task, "output_key", task_key))
        index_key = _optional_task_value(task, "results_index_key")
        engine = _engine_name(task, task_key)
        args = _task_args(task)

        input_content = load_runtime_content(input_key)
        engine_call = load_engine_call(engine, args=args)
        outcome = engine_call(input_content)

        # Smoke-test scope: local scripts return RedisModel-compatible
        # response/failure objects and development mode fails loud if the
        # contract is violated. Production retry/escalation policy belongs in
        # orchestrator routing, not here.
        try:
            outcome.save(output_key)
        except AttributeError as exc:
            raise TypeError(
                f"Engine {engine!r} returned {type(outcome).__name__}, "
                "not a RedisModel-compatible response/failure object"
            ) from exc

        post_worker_outcome(
            task_key=task_key,
            cursor_key=cursor_key,
            step_number=step_number,
            output_key=output_key,
            index_key=index_key,
        )

        return WorkerResult(
            processed=1,
            cursor_key=cursor_key,
            task_key=task_key,
            output_key=output_key,
        )


def _load_task(task_key: str) -> dict[str, Any]:
    data = RedisKey(task_key).hgetall()
    if not data:
        raise ValueError(f"worker task is missing or empty: {task_key}")
    return data


def _required_task_value(task: dict[str, Any], field: str, task_key: str) -> Any:
    value = task.get(field)
    if value is None or str(value) == "":
        raise ValueError(f"worker task missing required field {field!r}: {task_key}")
    return value


def _optional_task_value(task: dict[str, Any], field: str) -> str | None:
    value = task.get(field)
    if value is None or not str(value).strip():
        return None
    return str(value).strip()


def _engine_name(task: dict[str, Any], task_key: str) -> str:
    engine = task.get("engine")
    if engine:
        return str(engine)

    handler = task.get("handler")
    if handler:
        return str(handler).split(".", 1)[0]

    raise ValueError(f"worker task missing required field 'engine': {task_key}")


def _task_args(task: dict[str, Any]) -> dict[str, Any]:
    args_json = task.get("args_json")
    if args_json:
        try:
            payload = json.loads(str(args_json))
        except (TypeError, ValueError) as exc:
            raise ValueError("worker task args_json is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("worker task args_json must decode to an object")
        return payload

    args = task.get("args")
    if isinstance(args, dict):
        return args

    handler = task.get("handler")
    engine = task.get("engine")
    if handler and (engine == "scripts" or str(handler).startswith("scripts.")):
        return {"script": str(handler)}

    return {}


__all__ = ["WorkerExecutor", "WorkerResult"]
