"""Scrivener task factories used by orchestrator handlers."""

from __future__ import annotations

from typing import Any

from asc.models.process.task import Task

from ..contracts import (
    SCRIVENER_CALL_COMPLETED,
    SCRIVENER_CALL_FAILED,
    SCRIVENER_WRITE_CALL,
    SCRIVENER_WRITE_STEP,
)


SCRIVENER_PACKAGE = "scrivener"


def _scrivener_task(*, cursor: Any, action: str) -> Task:
    return Task(
        package=SCRIVENER_PACKAGE,
        action=action,
        cursor_key=str(cursor.redis_key),
    )


def make_scrivener_write_call(cursor: Any) -> Task:
    return _scrivener_task(
        cursor=cursor,
        action=SCRIVENER_WRITE_CALL,
    )


def make_scrivener_write_step(*, cursor: Any, **_ignored: Any) -> Task:
    return _scrivener_task(
        cursor=cursor,
        action=SCRIVENER_WRITE_STEP,
    )


def make_scrivener_call_completed(*, cursor: Any, **_ignored: Any) -> Task:
    return _scrivener_task(
        cursor=cursor,
        action=SCRIVENER_CALL_COMPLETED,
    )


def make_scrivener_call_failed(*, cursor: Any, **_ignored: Any) -> Task:
    return _scrivener_task(
        cursor=cursor,
        action=SCRIVENER_CALL_FAILED,
    )


__all__ = [
    "make_scrivener_call_completed",
    "make_scrivener_call_failed",
    "make_scrivener_write_call",
    "make_scrivener_write_step",
]