"""Orchestrator inbox contract and message router.

The inbox hot path stays intentionally cheap: validate and branch with simple
string operations. Handler modules may do heavier model/key loading after the
message kind is known.
"""

from importlib import import_module

from asc.orchestrator.errors import OrchestratorContractError
from asc.redis.key import RedisKey


HANDLER_MODULES = {
    "call": "asc.orchestrator.handlers.call",
    "committed": "asc.orchestrator.handlers.committed",
    "response": "asc.orchestrator.handlers.response",
    "failure": "asc.orchestrator.handlers.failure",
}

ALLOWED_POST_KINDS = frozenset(HANDLER_MODULES)


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

    if kind not in ALLOWED_POST_KINDS:
        allowed = ", ".join(sorted(ALLOWED_POST_KINDS))
        raise OrchestratorContractError(
            f"orchestrator inbox expected one of {allowed}; got {kind!r}: {raw}"
        )

    return raw, kind


def key_kind(raw_key: str | RedisKey) -> str:
    """Return the first key segment for lightweight logging or metrics.

    This helper validates only enough to prove that a first segment exists. Use
    ``require_post_key`` on the posting/routing path.
    """

    raw = str(raw_key).strip()
    kind, sep, _rest = raw.partition(":")
    if not sep or not kind:
        raise OrchestratorContractError(
            f"orchestrator expected kind:identity key; got {raw!r}"
        )
    return kind


def handle_message(raw_key: str | RedisKey) -> None:
    """Route one claimed orchestrator inbox key.

    Branching is done from the kind already computed by ``require_post_key``.
    RedisKey construction happens only after the handler kind is known.
    """

    raw, kind = require_post_key(raw_key)
    module_name = HANDLER_MODULES[kind]

    try:
        module = import_module(module_name)
    except ModuleNotFoundError as exc:
        raise OrchestratorContractError(
            f"orchestrator handler module is missing for {kind!r}: {module_name}"
        ) from exc

    handle = getattr(module, "handle", None)
    if not callable(handle):
        raise OrchestratorContractError(
            f"orchestrator handler module has no callable handle(): {module_name}"
        )

    handle(RedisKey(raw))


__all__ = [
    "ALLOWED_POST_KINDS",
    "HANDLER_MODULES",
    "require_post_key",
    "key_kind",
    "handle_message",
]
