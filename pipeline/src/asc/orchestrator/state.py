from __future__ import annotations

from importlib import import_module
from typing import Any

from asc.orchestrator.errors import OrchestratorContractError

CALL_STATE_CLASS_CANDIDATES = (
    ("asc.models.runtime.call_state", "RuntimeCallState"),
    ("asc.models.runtime.state", "RuntimeCallState"),
    ("asc.models.runtime.call", "RuntimeCallState"),
    ("asc.models.runtime.call", "CallState"),
)


def load_call_state(call_state_key: str) -> Any:
    """Load the mutable runtime call_state object from its Redis key."""

    for module_name, class_name in CALL_STATE_CLASS_CANDIDATES:
        try:
            cls = getattr(import_module(module_name), class_name)
        except (ModuleNotFoundError, AttributeError):
            continue

        for method_name in ("load_from_key", "load", "from_key"):
            method = getattr(cls, method_name, None)
            if callable(method):
                return method(call_state_key)

        try:
            from asc.redis.key import RedisKey
        except ModuleNotFoundError:
            continue
        return RedisKey(call_state_key).load_model(cls)  # type: ignore[attr-defined]

    raise OrchestratorContractError(
        "no RuntimeCallState model available; expected one of "
        + ", ".join(f"{m}.{c}" for m, c in CALL_STATE_CLASS_CANDIDATES)
    )


def save_call_state(call_state: Any) -> None:
    """Persist a mutated call_state using the model/state API available in-tree."""

    for method_name in ("save", "store", "persist", "write"):
        method = getattr(call_state, method_name, None)
        if callable(method):
            method()
            return

    key = call_state_key(call_state)
    try:
        from asc.redis.key import RedisKey
    except ModuleNotFoundError as exc:
        raise OrchestratorContractError("call_state has no save/store method") from exc

    RedisKey(key).store_model(call_state)  # type: ignore[attr-defined]


def call_state_key(call_state: Any) -> str:
    for name in ("key", "redis_key", "call_state_key", "runtime_key"):
        value = getattr(call_state, name, None)
        if callable(value):
            value = value()
        if value:
            return _to_str(value)
    identity = call_identity(call_state)
    if identity:
        return f"runtime:{identity}:state"
    raise OrchestratorContractError("call_state has no key or identity")


def call_identity(call_state: Any) -> str:
    for name in ("call_identity", "identity", "record_identity"):
        value = getattr(call_state, name, None)
        if value:
            return _to_str(value)
    raise OrchestratorContractError("call_state has no call identity")


def current_step_number(call_state: Any) -> int:
    for name in ("step_number", "current_step_number", "plan_step_number"):
        value = getattr(call_state, name, None)
        if value is not None:
            return int(value)
    raise OrchestratorContractError("call_state has no current step number")


def set_current_step_number(call_state: Any, step_number: int) -> None:
    for name in ("step_number", "current_step_number", "plan_step_number"):
        if hasattr(call_state, name):
            setattr(call_state, name, int(step_number))
            return
    raise OrchestratorContractError("call_state has no mutable step number")


def mark_started(call_state: Any) -> None:
    for name in ("status", "state", "call_status"):
        if hasattr(call_state, name):
            setattr(call_state, name, "running")
            return


def mark_completed(call_state: Any) -> None:
    for name in ("status", "state", "call_status"):
        if hasattr(call_state, name):
            setattr(call_state, name, "complete")
            return


def mark_failed(call_state: Any) -> None:
    for name in ("status", "state", "call_status"):
        if hasattr(call_state, name):
            setattr(call_state, name, "failed")
            return


def is_failed(call_state: Any) -> bool:
    for name in ("failed", "is_failed"):
        value = getattr(call_state, name, None)
        if callable(value):
            return bool(value())
        if value is not None:
            return bool(value)
    for name in ("status", "state", "call_status"):
        value = getattr(call_state, name, None)
        if value is not None and str(value).lower() in {"failed", "failure", "error", "exhausted"}:
            return True
    return False


def failure_message(call_state: Any) -> str:
    for name in ("failure_message", "fail_message", "error", "worker_error", "last_error"):
        value = getattr(call_state, name, None)
        if value:
            return _to_str(value)
    return "worker reported terminal failure"


def plan_key(call_state: Any) -> str:
    for name in ("plan_key", "plan", "plan_identity", "plan_slug"):
        value = getattr(call_state, name, None)
        if value:
            return _to_str(value)
    raise OrchestratorContractError("call_state has no plan key")


def _to_str(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
