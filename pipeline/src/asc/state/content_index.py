from __future__ import annotations

from asc.state.runtime_indices import RuntimeContentIndex


def hkeys(call_identity: str) -> list[str]:
    return RuntimeContentIndex(call_identity).hkeys()


def hlen(call_identity: str) -> int:
    return RuntimeContentIndex(call_identity).hlen()


def resolve_key(call_identity: str, position: int) -> str:
    return RuntimeContentIndex(call_identity).resolve_key(position)


def bind_key(call_identity: str, position: int, full_key: str) -> str:
    return RuntimeContentIndex(call_identity).bind_key(position, full_key)


__all__ = ["bind_key", "hkeys", "hlen", "resolve_key"]
