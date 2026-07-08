"""Worker task factories used by the orchestrator."""

from __future__ import annotations

from asc.models.control.step import Step
from asc.models.process.task import WorkerTask
from asc.redis.key import RedisKey
from asc.worker.engines import normalize_engine_kind

from ..contracts import WORKER_EXECUTE_STEP


RESULT_KIND_BY_ENGINE = {
    "llm": "response",
    "script": "transform",
    "rag": "retrieval",
}


def make_worker_step(
    *,
    step_key: str,
    data_key: str,
) -> WorkerTask:
    """Create a Worker execute_step task for one materialized Step."""

    expected_key = _expected_worker_result_key(step_key=step_key, data_key=data_key)
    failure_key = _worker_failure_key(step_key=step_key, data_key=data_key)
    return WorkerTask(
        package="worker",
        action=WORKER_EXECUTE_STEP,
        expected_key=expected_key,
        failure_key=failure_key,
        step_key=step_key,
        data_key=data_key,
    )


def _expected_worker_result_key(*, step_key: str, data_key: str) -> str:
    step = Step.load(step_key)
    engine = normalize_engine_kind(step.engine)
    result_kind = RESULT_KIND_BY_ENGINE.get(engine)
    if result_kind is None:
        raise ValueError(f"unsupported worker step engine: {step.engine!r}")

    return RedisKey(
        kind=result_kind,
        identity=RedisKey(data_key).identity,
        suffix=_step_suffix(step_key=step_key, step=step),
    ).raw_key


def _worker_failure_key(*, step_key: str, data_key: str) -> str:
    step = Step.load(step_key)
    return RedisKey(
        kind="failure",
        identity=RedisKey(data_key).identity,
        suffix=_step_suffix(step_key=step_key, step=step),
    ).raw_key


def _step_suffix(*, step_key: str, step: Step) -> str:
    for name in ("step_number", "number"):
        value = getattr(step, name, None)
        if value not in (None, ""):
            return str(value)

    suffix = RedisKey(step_key).suffix
    if not suffix:
        raise ValueError(f"worker task step_key has no step suffix: {step_key!r}")

    return str(suffix)


__all__ = ["make_worker_step"]
