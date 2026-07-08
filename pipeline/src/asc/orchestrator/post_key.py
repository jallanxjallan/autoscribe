"""Shared orchestrator post-key validation.

This module has no handler imports. Inbox modules may import it without pulling
in the live orchestrator router and its downstream package dependencies.
"""

from asc.redis.key import RedisKey

from .contracts import ORCHESTRATOR_POST_KINDS
from .errors import OrchestratorContractError


def require_post_key(key: str | RedisKey) -> tuple[str, str]:
    """Validate a claimed or posted orchestrator inbox key."""

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


__all__ = ["key_kind", "require_post_key"]
