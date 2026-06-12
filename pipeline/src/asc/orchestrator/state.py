from __future__ import annotations

from typing import Any

from asc.models.runtime.call import CallRecord
from asc.models.runtime.cursor import RuntimeCallState
from asc.orchestrator.errors import OrchestratorContractError


def load_call_state(call_state_key: str) -> RuntimeCallState:
    """Load the mutable runtime call_state from its full Redis key."""

    return RuntimeCallState.load(call_state_key)


def save_call_state(call_state: RuntimeCallState) -> None:
    """Persist the mutable runtime call_state through its model API."""

    call_state.save()


def call_state_key(call_state: RuntimeCallState) -> str:
    return _required_str(call_state, "key")


def call_key(call_state: RuntimeCallState) -> str:
    """Full immutable CallRecord key referenced by this mutable state."""

    return _required_str(call_state, "call_key")


def call_record(call_state: RuntimeCallState) -> CallRecord:
    return CallRecord.load(call_key(call_state))


def call_identity(call_state: RuntimeCallState) -> str:
    return _required_str(call_record(call_state), "identity")


def current_step_number(call_state: RuntimeCallState) -> int:
    return int(_required_value(call_state, "step_number"))


def set_current_step_number(call_state: RuntimeCallState, step_number: int) -> None:
    _set_required(call_state, "step_number", int(step_number))


def current_step_key(call_state: RuntimeCallState) -> str:
    return _required_str(call_state, "step_key")


def input_content_key(call_state: RuntimeCallState) -> str:
    """Return the immutable prompt key from the CallRecord.

    The mutable call_state deliberately does not carry prompt_key.  It carries
    only execution pointers/status.  The original prompt belongs to the
    immutable call record.
    """

    return _required_str(call_record(call_state), "prompt_key")


def output_content_key(call_state: RuntimeCallState) -> str:
    return _required_str(call_state, "response_key")


def set_worker_keys(
    call_state: RuntimeCallState,
    *,
    step_key: str,
    response_key: str,
) -> None:
    """Expose only full execution keys to the worker."""

    _set_required(call_state, "step_key", step_key)
    _set_required(call_state, "response_key", response_key)


def status(call_state: RuntimeCallState) -> str:
    value = getattr(call_state, "status", None)
    return str(value).strip().lower() if value is not None else ""


def is_started(call_state: RuntimeCallState) -> bool:
    return status(call_state) in {"running", "success", "failed", "complete", "completed"}


def is_success(call_state: RuntimeCallState) -> bool:
    return status(call_state) == "success"


def mark_started(call_state: RuntimeCallState) -> None:
    _set_required(call_state, "status", "running")


def mark_completed(call_state: RuntimeCallState) -> None:
    _set_required(call_state, "status", "complete")


def mark_failed(call_state: RuntimeCallState) -> None:
    _set_required(call_state, "status", "failed")


def is_failed(call_state: RuntimeCallState) -> bool:
    return status(call_state) == "failed"


def failure_message(call_state: RuntimeCallState) -> str:
    value = getattr(call_state, "failure_message", None)
    return str(value) if value else "worker reported terminal failure"


def _required_value(obj: Any, name: str) -> Any:
    if not hasattr(obj, name):
        raise OrchestratorContractError(f"{type(obj).__name__} missing required field: {name}")
    value = getattr(obj, name)
    if value is None:
        raise OrchestratorContractError(f"{type(obj).__name__} field is empty: {name}")
    return value


def _required_str(obj: Any, name: str) -> str:
    value = _required_value(obj, name)
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    text = str(value).strip()
    if not text:
        raise OrchestratorContractError(f"{type(obj).__name__} field is empty: {name}")
    return text


def _set_required(obj: Any, name: str, value: Any) -> None:
    if not hasattr(obj, name):
        raise OrchestratorContractError(f"{type(obj).__name__} missing required field: {name}")
    setattr(obj, name, value)
