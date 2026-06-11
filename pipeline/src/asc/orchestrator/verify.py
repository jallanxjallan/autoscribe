from __future__ import annotations

from asc.models.runtime.content import RuntimeContentRecord
from asc.orchestrator.errors import OrchestratorContractError
from asc.orchestrator.state import input_content_key, output_content_key


def verify_input_artifact(call_state) -> str:
    """Verify the full input content key currently exposed on call_state."""

    key = input_content_key(call_state)
    _load_content(key)
    return key


def verify_output_artifact(call_state) -> str:
    """Verify the full output content key currently exposed on call_state."""

    key = output_content_key(call_state)
    _load_content(key)
    return key


def _load_content(key: str) -> None:
    try:
        RuntimeContentRecord.load(key)
    except KeyError as exc:
        raise OrchestratorContractError(f"missing content artifact: {key}") from exc
