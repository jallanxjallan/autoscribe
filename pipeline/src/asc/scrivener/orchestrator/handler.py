"""Orchestrator inbox contract and message router.

The orchestrator accepts only runtime call notices and daemon outcomes:

    call:<identity>[:record]
    outcome:<task_identity>

All daemon completion routing is driven by the Outcome record, not by artifact
key kinds such as response, failure, committed, transform, or retrieval.
"""

from asc.orchestrator.errors import OrchestratorContractError
from asc.redis.key import RedisKey

from .contracts import CALL, ORCHESTRATOR_POST_KINDS, OUTCOME
from .handlers import call as call_handler
from .handlers import outcome as outcome_handler


def require_post_key(key: str | RedisKey) -> tuple[str, str]:
    """Validate a key before posting it to the orchestrator inbox.

    Returns ``(raw, kind)`` so callers on the hot path do not have to split the
    same key twice.
    """

    raw = str(key).strip()
    if not raw:
        raise OrchestratorContractError("orchestrator inbox expected a non-empty key")

    kind, sep, rest = raw.partition(":")
    if not sep or not kind or not rest:
        raise OrchestratorContractError(
            f"orchestrator inbox expected kind:identity key; got {raw!r}"
        )

    identity = rest.split(":", 1)[0]
    if not identity:
        raise OrchestratorContractError(
            f"orchestrator inbox expected non-empty identity; got {raw!r}"
        )

    if kind not in ORCHESTRATOR_POST_KINDS:
        allowed = ", ".join(sorted(ORCHESTRATOR_POST_KINDS))
        raise OrchestratorContractError(
            f"orchestrator inbox expected one of {allowed}; got {kind!r}: {raw}"
        )

    return raw, kind


def key_kind(raw_key: str | RedisKey) -> str:
    """Return the first key segment for lightweight logging or metrics."""

    raw = str(raw_key).strip()
    kind, sep, _rest = raw.partition(":")
    if not sep or not kind:
        raise OrchestratorContractError(
            f"orchestrator expected kind:identity key; got {raw!r}"
        )
    return kind


def handle_message(raw_key: str | RedisKey) -> None:
    """Route one claimed orchestrator inbox key."""

    raw, kind = require_post_key(raw_key)
    key = RedisKey(raw)

    if kind == CALL:
        call_handler.handle(key)
        return

    if kind == OUTCOME:
        outcome_handler.handle(key)
        return

    raise OrchestratorContractError(f"unhandled orchestrator post kind {kind!r}")


__all__ = [
    "key_kind",
    "handle_message",
    "require_post_key",
]
