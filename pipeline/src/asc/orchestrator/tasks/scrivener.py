"""Scrivener task factories used by the orchestrator."""

from __future__ import annotations

from asc.models.process.task import ScrivenerTask
from asc.scrivener.maps import CALLS_TABLE, EXPORTS_TABLE, STEPS_TABLE

from ..contracts import (
    SCRIVENER_CALL_COMPLETED,
    SCRIVENER_CALL_FAILED,
    SCRIVENER_WRITE_CALL,
    SCRIVENER_WRITE_STEP,
)


def make_scrivener_write_call(*, data_key: str) -> ScrivenerTask:
    return _make_scrivener_task(
        action=SCRIVENER_WRITE_CALL,
        table=CALLS_TABLE,
        data_key=data_key,
    )


def make_scrivener_write_step(*, data_key: str) -> ScrivenerTask:
    return _make_scrivener_task(
        action=SCRIVENER_WRITE_STEP,
        table=STEPS_TABLE,
        data_key=data_key,
    )


def make_scrivener_call_completed(*, data_key: str) -> ScrivenerTask:
    return _make_scrivener_task(
        action=SCRIVENER_CALL_COMPLETED,
        table=EXPORTS_TABLE,
        data_key=data_key,
    )


def make_scrivener_call_failed(*, data_key: str) -> ScrivenerTask:
    return _make_scrivener_task(
        action=SCRIVENER_CALL_FAILED,
        table=EXPORTS_TABLE,
        data_key=data_key,
    )


def _make_scrivener_task(*, action: str, table: str, data_key: str) -> ScrivenerTask:
    return ScrivenerTask(
        package="scrivener",
        action=action,
        expected_key=data_key,
        table=table,
        data_key=data_key,
    )


__all__ = [
    "make_scrivener_call_completed",
    "make_scrivener_call_failed",
    "make_scrivener_write_call",
    "make_scrivener_write_step",
]
