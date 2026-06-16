from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from asc.redis.key import RedisKey
from asc.workers.engines import load_engine_call
from asc.workers.outcome import submit_outcome
from asc.workers.runtime_io import load_runtime_content


@dataclass(frozen=True, slots=True)
class WorkerResult:
    processed: int
    cursor_key: str
    job_key: str
    output_key: str


class WorkerExecutor:
    def execute(self, job_key: str) -> WorkerResult:
        job_key = str(job_key).strip()
        if not job_key:
            raise ValueError("worker claimed an empty job key")

        job = _load_job(job_key)
        cursor_key = str(_required_job_value(job, "cursor_key", job_key))
        step_number = int(_required_job_value(job, "step_number", job_key))
        input_key = str(_required_job_value(job, "input_key", job_key))
        output_key = str(_required_job_value(job, "output_key", job_key))
        engine = _engine_name(job, job_key)
        args = _job_args(job)

        input_content = load_runtime_content(input_key)
        engine_call = load_engine_call(engine, args=args)
        outcome = engine_call(input_content)

        # TODO:
        # Development mode fails fast so contract violations are immediately
        # visible. In production the worker should never die because an engine
        # returned an unexpected object. Instead, catch the exception, log it,
        # persist a StepFailure record, return the job to the orchestrator queue,
        # and allow the orchestrator to decide whether to retry, fail, or
        # escalate the call.
        try:
            outcome.save(output_key)
        except AttributeError as exc:
            raise TypeError(
                f"Engine {engine!r} returned {type(outcome).__name__}, "
                "not a RedisModel-compatible StepResult or StepFailure"
            ) from exc

        submit_outcome(job_key)

        return WorkerResult(
            processed=1,
            cursor_key=cursor_key,
            job_key=job_key,
            output_key=output_key,
        )


def _load_job(job_key: str) -> dict[str, Any]:
    data = RedisKey(job_key).hgetall()
    if not data:
        raise ValueError(f"worker job is missing or empty: {job_key}")
    return data


def _required_job_value(job: dict[str, Any], field: str, job_key: str) -> Any:
    value = job.get(field)
    if value is None or str(value) == "":
        raise ValueError(f"worker job missing required field {field!r}: {job_key}")
    return value


def _engine_name(job: dict[str, Any], job_key: str) -> str:
    engine = job.get("engine")
    if engine:
        return str(engine)

    handler = job.get("handler")
    if handler:
        return str(handler).split(".", 1)[0]

    raise ValueError(f"worker job missing required field 'engine': {job_key}")


def _job_args(job: dict[str, Any]) -> dict[str, Any]:
    args_json = job.get("args_json")
    if args_json:
        try:
            payload = json.loads(str(args_json))
        except (TypeError, ValueError) as exc:
            raise ValueError("worker job args_json is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("worker job args_json must decode to an object")
        return payload

    args = job.get("args")
    if isinstance(args, dict):
        return args

    handler = job.get("handler")
    engine = job.get("engine")
    if handler and (engine == "scripts" or str(handler).startswith("scripts.")):
        return {"script": str(handler)}

    return {}


__all__ = ["WorkerExecutor", "WorkerResult"]
