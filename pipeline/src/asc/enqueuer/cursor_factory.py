from __future__ import annotations

from asc.models.process.cursor import Cursor


def build_runtime_cursor(*, identity: str, call_key: str, plan_key: str) -> Cursor:
    return Cursor(
        identity=identity,
        call_key=call_key,
        plan_key=plan_key,
    )


def save_runtime_cursor(cursor: Cursor) -> str:
    cursor.save()
    return str(cursor.redis_key)


__all__ = ["build_runtime_cursor", "save_runtime_cursor"]
