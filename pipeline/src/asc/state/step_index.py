from __future__ import annotations

from asc.state.runtime_indices import RuntimeStepIndex


def hkeys(call_identity: str) -> list[str]:
    return RuntimeStepIndex(call_identity).hkeys()


def hlen(call_identity: str) -> int:
    return RuntimeStepIndex(call_identity).hlen()


def resolve_key(call_identity: str, step_number: int) -> str:
    return RuntimeStepIndex(call_identity).resolve_key(step_number)


def bind_key(call_identity: str, step_number: int, full_key: str) -> str:
    return RuntimeStepIndex(call_identity).bind_key(step_number, full_key)


__all__ = ["bind_key", "hkeys", "hlen", "resolve_key"]
