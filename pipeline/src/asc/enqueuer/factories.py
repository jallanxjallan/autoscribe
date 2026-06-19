from __future__ import annotations

from asc.models.process.cursor import Cursor
from asc.state.response_index import create_response_index as state_create_response_index


def build_response_index(
    *,
    identity: str,
    call_key: str,
    total_steps: int,
    ttl_seconds: int | None = None,
) -> str:
    return state_create_response_index(
        identity=identity,
        call_key=call_key,
        total_steps=total_steps,
        ttl_seconds=ttl_seconds,
    )


__all__ = []


def build_runtime_cursor(*, identity: str, call_key: str, plan_key: str) -> Cursor:
    return Cursor(
        identity=identity,
        call_key=call_key,
        plan_key=plan_key,
    )


def save_runtime_cursor(cursor: Cursor) -> str:
    cursor.save()
    return str(cursor.redis_key)


__all__ = ["build_runtime_cursor", "save_runtime_cursor", "build_response_index"]
