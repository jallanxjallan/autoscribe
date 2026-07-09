"""Scrivener task factories used by the orchestrator."""

from __future__ import annotations

from asc.ledger.maps import CALLS_TABLE, EXPORTS_TABLE, RESPONSES_TABLE
from asc.models.process.task import ScrivenerTask

from ..contracts import (
    SCRIVENER_CALL_COMPLETED,
    SCRIVENER_CALL_FAILED,
    SCRIVENER_CONFIRM_EXPORT,
    SCRIVENER_WRITE_CALL,
)


def make_scrivener_write_call(*, data_key: str) -> ScrivenerTask:
    return _make_scrivener_task(
        action=SCRIVENER_WRITE_CALL,
        table=CALLS_TABLE,
        data_key=data_key,
    )


def make_scrivener_call_completed(*, data_key: str) -> ScrivenerTask:
    return _make_scrivener_task(
        action=SCRIVENER_CALL_COMPLETED,
        table=RESPONSES_TABLE,
        data_key=data_key,
    )


def make_scrivener_call_failed(*, data_key: str) -> ScrivenerTask:
    return _make_scrivener_task(
        action=SCRIVENER_CALL_FAILED,
        table=RESPONSES_TABLE,
        data_key=data_key,
    )


def make_scrivener_confirm_export(*, data_key: str) -> ScrivenerTask:
    return _make_scrivener_task(
        action=SCRIVENER_CONFIRM_EXPORT,
        table=EXPORTS_TABLE,
        data_key=data_key,
    )


def _make_scrivener_task(*, action: str, table: str, data_key: str) -> ScrivenerTask:
    # table remains on the task because the existing task model carries it;
    # ledger derives and validates the table from action.
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
    "make_scrivener_confirm_export",
    "make_scrivener_write_call",
]
