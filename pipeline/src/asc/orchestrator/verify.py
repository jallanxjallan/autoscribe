from __future__ import annotations

from typing import Any

from asc.orchestrator.errors import OrchestratorContractError
from asc.orchestrator.state import call_identity, current_step_number


def verify_input_artifact(call_state: Any) -> str:
    """Verify the input artifact for the current step.

    With content.0 as original text, step N consumes content.(N-1).
    """

    step_number = current_step_number(call_state)
    return _content_key_for_position(call_identity(call_state), step_number - 1)


def verify_output_artifact(call_state: Any) -> str:
    """Verify the output artifact produced by the just-finished worker.

    With content.0 as original text, step N produces content.N.  The artifact is
    the source of truth; worker annotations are only claims.
    """

    step_number = current_step_number(call_state)
    return _content_key_for_position(call_identity(call_state), step_number)


def _content_key_for_position(identity: str, position: int) -> str:
    if position < 0:
        raise OrchestratorContractError(
            f"invalid content position {position} for call={identity}"
        )

    value = _lookup_content_key(identity, position)
    if value is None:
        raise OrchestratorContractError(
            f"missing content artifact for call={identity} position={position}"
        )
    return value


def _lookup_content_key(identity: str, position: int) -> str | None:
    try:
        from asc.state.content_index import get_content_key
    except ImportError:
        try:
            from asc.state.runtime_indices import RuntimeContentIndex
        except ImportError:
            return _fallback_content_key_if_loadable(identity, position)
        index = RuntimeContentIndex(identity)
        value = index.get_key(position)
    else:
        value = get_content_key(identity, position)

    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _fallback_content_key_if_loadable(identity: str, position: int) -> str | None:
    key = f"runtime:{identity}:content.{position}"
    try:
        from asc.models.runtime.content import RuntimeContentRecord
        from asc.redis.key import RedisKey
    except ModuleNotFoundError:
        return key

    try:
        for method_name in ("load_from_key", "load"):
            method = getattr(RuntimeContentRecord, method_name, None)
            if callable(method):
                method(key)
                return key
        RedisKey(key).load_model(RuntimeContentRecord)  # type: ignore[attr-defined]
    except Exception:
        return None
    return key
