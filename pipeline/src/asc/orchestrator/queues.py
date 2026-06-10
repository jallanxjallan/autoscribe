from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable

from asc.orchestrator.errors import OrchestratorContractError


@dataclass(frozen=True)
class ClaimedSignal:
    identity: str
    score: object | None = None


START_QUEUE_MODULES = (
    "asc.state.call_state_start_queue",
    "asc.state.call_queue",
    "asc.state.orchestrator_call_queue",
    "asc.state.start_queue",
)

WORKER_QUEUE_MODULES = (
    "asc.state.worker_queue",
    "asc.state.call_state_worker_queue",
    "asc.state.step_queue",  # compatibility: now carries call_state keys
)

RESPONSE_QUEUE_MODULES = (
    "asc.state.call_state_response_queue",
    "asc.state.response_queue",
    "asc.state.orchestrator_queue",
)


def _load_first_callable(module_names: tuple[str, ...], attr_names: tuple[str, ...]) -> Callable[..., Any]:
    for module_name in module_names:
        try:
            module = import_module(module_name)
        except ModuleNotFoundError:
            continue
        for attr_name in attr_names:
            attr = getattr(module, attr_name, None)
            if callable(attr):
                return attr
    raise OrchestratorContractError(
        "no queue accessor found; tried " + ", ".join(module_names)
    )


def _normalize_claim(value: Any) -> ClaimedSignal | None:
    if value is None:
        return None
    if isinstance(value, str):
        return ClaimedSignal(identity=value)
    if isinstance(value, bytes):
        return ClaimedSignal(identity=value.decode("utf-8"))

    identity = getattr(value, "identity", None)
    if identity is None:
        identity = getattr(value, "key", None)
    if identity is None:
        identity = getattr(value, "call_state_key", None)
    if identity is None:
        identity = getattr(value, "call_key", None)
    if identity is None:
        identity = str(value)

    if isinstance(identity, bytes):
        identity = identity.decode("utf-8")

    return ClaimedSignal(identity=str(identity), score=getattr(value, "score", None))


def _claim(module_names: tuple[str, ...]) -> ClaimedSignal | None:
    claim = _load_first_callable(module_names, ("claim_next", "claim", "pop", "dequeue"))
    return _normalize_claim(claim())


def _enqueue(module_names: tuple[str, ...], key: str, *, score: object | None = None) -> None:
    enqueue = _load_first_callable(module_names, ("enqueue", "push", "put"))
    try:
        enqueue(key, score=score)
    except TypeError:
        enqueue(key)


def claim_start() -> ClaimedSignal | None:
    """Claim one newly materialized call_state key for orchestration start."""

    try:
        return _claim(START_QUEUE_MODULES)
    except OrchestratorContractError:
        return None


def claim_response() -> ClaimedSignal | None:
    """Claim one worker-returned call_state key."""

    try:
        return _claim(RESPONSE_QUEUE_MODULES)
    except OrchestratorContractError:
        return None


def enqueue_worker(call_state_key: str, *, score: object | None = None) -> None:
    """Place the mutable call_state key on the worker queue.

    Compatibility note: older trees may still call this queue `step_queue`, but
    the payload is now a call_state key, not a runtime step key.
    """

    _enqueue(WORKER_QUEUE_MODULES, call_state_key, score=score)


def requeue_start(call_state_key: str, *, score: object | None = None) -> None:
    _enqueue(START_QUEUE_MODULES, call_state_key, score=score)


def requeue_response(call_state_key: str, *, score: object | None = None) -> None:
    _enqueue(RESPONSE_QUEUE_MODULES, call_state_key, score=score)
