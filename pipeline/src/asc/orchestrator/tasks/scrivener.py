"""Scrivener task factories used by orchestrator handlers."""

from __future__ import annotations

from typing import Any

import ulid

from asc.models.process.task import Task

from ..contracts import (
    SCRIVENER_CALL_COMPLETED,
    SCRIVENER_CALL_FAILED,
    SCRIVENER_WRITE_CALL,
    SCRIVENER_WRITE_STEP,
)


SCRIVENER_PACKAGE = "scrivener"


def make_scrivener_write_call(cursor: Any) -> Task:
    return Task(
        identity=str(ulid.new()),
        package=SCRIVENER_PACKAGE,
        action=SCRIVENER_WRITE_CALL,
        cursor_key=cursor.raw_key,
    )


def make_scrivener_write_step(*, cursor: Any, **_ignored: Any) -> Task:
    return Task(
        identity=str(ulid.new()),
        package=SCRIVENER_PACKAGE,
        action=SCRIVENER_WRITE_STEP,
        cursor_key=cursor.raw_key,
    )


def make_scrivener_call_completed(*, cursor: Any, **_ignored: Any) -> Task:
    return Task(
        identity=str(ulid.new()),
        package=SCRIVENER_PACKAGE,
        action=SCRIVENER_CALL_COMPLETED,
        cursor_key=cursor.raw_key,
    )


def make_scrivener_call_failed(*, cursor: Any, **_ignored: Any) -> Task:
    return Task(
        identity=str(ulid.new()),
        package=SCRIVENER_PACKAGE,
        action=SCRIVENER_CALL_FAILED,
        cursor_key=cursor.raw_key,
    )


__all__ = [
    "make_scrivener_call_completed",
    "make_scrivener_call_failed",
    "make_scrivener_write_call",
    "make_scrivener_write_step",
]
