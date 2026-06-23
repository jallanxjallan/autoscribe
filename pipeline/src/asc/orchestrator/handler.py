"""Top-level orchestrator inbox message handling.

The orchestrator inbox carries Redis keys. The Redis key kind selects the broad
message class. The identity and suffix are otherwise opaque to the dispatcher and
are passed unchanged to the selected handler.
"""

from asc.redis.key import RedisKey

from .contracts import ORCHESTRATOR_POST_KINDS
from .errors import OrchestratorContractError


def parse_message_key(key: str | RedisKey) -> RedisKey:
    """Return a RedisKey for an orchestrator inbox message.

    Orchestrator posts may be either two-segment notices such as
    ``outcome:<identity>`` or canonical three-segment record keys such as
    ``call:<identity>:record``. The dispatcher cares only about ``kind``.
    """

    raw = str(key).strip()
    if not raw:
        raise OrchestratorContractError("orchestrator message key must be non-empty")

    try:
        parsed = key if isinstance(key, RedisKey) else RedisKey(raw)
    except ValueError as exc:
        raise OrchestratorContractError(
            f"orchestrator message must be a Redis key: {raw!r}"
        ) from exc

    if not parsed.kind or not parsed.identity:
        raise OrchestratorContractError(
            f"orchestrator message must have non-empty kind and identity: {raw!r}"
        )

    return parsed


def split_message_key(key: str | RedisKey) -> tuple[str, str]:
    """Return ``(kind, identity)`` from an orchestrator message key.

    The suffix, when present, is deliberately ignored. This keeps older callers
    that only need broad routing semantics working while allowing canonical
    record keys like ``call:<identity>:record`` through the inbox.
    """

    parsed = parse_message_key(key)
    return parsed.kind, parsed.identity


def require_post_key(key: str | RedisKey) -> str:
    """Validate and return a normalized orchestrator inbox message key."""

    parsed = parse_message_key(key)
    if parsed.kind not in ORCHESTRATOR_POST_KINDS:
        expected = ", ".join(sorted(ORCHESTRATOR_POST_KINDS))
        raise OrchestratorContractError(
            f"orchestrator inbox expected one of {expected}; "
            f"got {parsed.kind!r}: {parsed}"
        )
    return str(parsed)


def handle_message(key: str | RedisKey) -> None:
    """Dispatch one orchestrator inbox message to its kind handler."""

    posted_key = parse_message_key(require_post_key(key))

    from .handlers import HANDLERS

    try:
        handler = HANDLERS[posted_key.kind]
    except KeyError as exc:
        expected = ", ".join(sorted(HANDLERS))
        raise OrchestratorContractError(
            f"no orchestrator handler for kind {posted_key.kind!r}; "
            f"expected {expected}: {posted_key}"
        ) from exc

    handler(posted_key)


__all__ = ["handle_message", "parse_message_key", "require_post_key", "split_message_key"]
