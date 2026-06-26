"""Orchestrator inbox contract and message handler.

The orchestrator accepts runtime call notices and daemon task outcomes:

    call:<identity>[:record]
    outcome:<task_identity>

``Outcome`` is only a receipt. The handler loads the associated task and routes
completion decisions by task package.
"""

from asc.models.process.task import Outcome, ScrivenerTask, WorkerTask
from asc.redis.key import RedisKey
from asc.redis.primitives import hashes

from .contracts import CALL, OUTCOME
from .handlers import call as call_handler
from .handlers import scrivener as scrivener_handler
from .handlers import worker as worker_handler
from .post_key import require_post_key

SCRIVENER_PACKAGE = "scrivener"
WORKER_PACKAGE = "worker"
TASK = "task"



def handle(raw_key: str | RedisKey) -> None:
    """Handle one claimed orchestrator inbox key."""

    raw, kind = require_post_key(raw_key)
    key = RedisKey(raw)

    if kind == CALL:
        call_handler.handle(key)
        return

    if kind == OUTCOME:
        _handle_outcome(key)
        return

    raise OrchestratorContractError(f"unhandled orchestrator post kind {kind!r}")


def _handle_outcome(key: RedisKey) -> None:
    outcome = Outcome.load(str(key))
    task = _load_task_for_outcome(outcome)

    if isinstance(task, ScrivenerTask):
        scrivener_handler.handle_done(task=task, outcome=outcome)
        return

    if isinstance(task, WorkerTask):
        worker_handler.handle_done(task=task, outcome=outcome)
        return

    raise OrchestratorContractError(
        f"unknown task type for outcome {key}: {type(task).__name__}"
    )


def _load_task_for_outcome(outcome: Outcome) -> ScrivenerTask | WorkerTask:
    task_key = RedisKey(kind=TASK, identity=outcome.identity)
    raw = hashes.hgetall(task_key)
    if not raw:
        raise OrchestratorContractError(f"missing task for outcome: {task_key.raw_key}")

    package = _required_text(raw.get("package"), "task.package")
    if package == SCRIVENER_PACKAGE:
        return ScrivenerTask.model_validate(raw)
    if package == WORKER_PACKAGE:
        return WorkerTask.model_validate(raw)

    raise OrchestratorContractError(
        f"unknown task package {package!r} for outcome: {task_key.raw_key}"
    )


def _required_text(value: object, field_name: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise OrchestratorContractError(f"{field_name} must be non-empty")
    return text


__all__ = [
    "handle",
    "require_post_key",
]
