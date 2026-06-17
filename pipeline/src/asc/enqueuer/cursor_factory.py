from __future__ import annotations

from asc.enqueuer.keys import ResolvedEnqueueKeys
from asc.models.process.cursor import Cursor


def build_runtime_cursor(keys: ResolvedEnqueueKeys) -> Cursor:
    return Cursor(
        identity=keys.call_identity,
        call_key=keys.call_key,
        plan_key=keys.plan_key,
    )


def save_runtime_cursor(cursor: Cursor) -> str:
    cursor.save()
    return str(cursor.redis_key)


__all__ = ["build_runtime_cursor", "save_runtime_cursor"]
