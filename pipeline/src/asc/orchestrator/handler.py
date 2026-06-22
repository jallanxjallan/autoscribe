"""Top-level orchestrator inbox message handling.

The orchestrator inbox carries message keys in the form ``kind:identity``.
``kind`` is only the broad message class. ``identity`` is opaque to the dispatcher and is
passed unchanged to the selected handler. Outcome task semantics are resolved only
after the Outcome record is loaded.
"""

from asc.redis.key import RedisKey

from .contracts import ORCHESTRATOR_POST_KINDS
from .errors import OrchestratorContractError


def split_message_key(key: str | RedisKey) -> tuple[str, str]:
    """Return ``(kind, identity)`` from a two-segment orchestrator message key."""

    raw = str(key).strip()
    try:
        kind, identity = raw.split(":", 1)
    except ValueError as exc:
        raise OrchestratorContractError(
            f"orchestrator message must be kind:identity: {raw!r}"
        ) from exc

    kind = kind.strip()
    identity = identity.strip()

    if not kind or not identity:
        raise OrchestratorContractError(
            f"orchestrator message must have non-empty kind and identity: {raw!r}"
        )
    if ":" in identity:
        raise OrchestratorContractError(
            f"orchestrator message must have exactly two segments: {raw!r}"
        )

    return kind, identity


def require_post_key(key: str | RedisKey) -> str:
    """Validate and return a normalized orchestrator inbox message key."""

    raw = str(key).strip()
    kind, _identity = split_message_key(raw)
    if kind not in ORCHESTRATOR_POST_KINDS:
        expected = ", ".join(sorted(ORCHESTRATOR_POST_KINDS))
        raise OrchestratorContractError(
            f"orchestrator inbox expected one of {expected}; got {kind!r}: {raw}"
        )
    return raw


def handle_message(key: str | RedisKey) -> None:
    """Dispatch one orchestrator inbox message to its kind handler."""

    raw = require_post_key(key)
    kind, identity = split_message_key(raw)

    from .handlers import HANDLERS

    try:
        handler = HANDLERS[kind]
    except KeyError as exc:
        expected = ", ".join(sorted(HANDLERS))
        raise OrchestratorContractError(
            f"no orchestrator handler for kind {kind!r}; expected {expected}: {raw}"
        ) from exc

    handler(identity)


__all__ = ["handle_message", "require_post_key", "split_message_key"]
