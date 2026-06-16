"""Patch pattern for asc.scrivener.daemon/runtime.

This is intentionally a splice, not a full replacement, because current local
runtime names may differ. The invariant is: every claimed job returns its cursor
(or cursor key) to orchestrator even if the ledger write failed.
"""

from __future__ import annotations

import logging
from typing import Any

from asc.scrivener.execute import ScrivenerExecutor
from asc.state.orchestrator_queue import insert as enqueue_orchestrator

log = logging.getLogger(__name__)


def cursor_key_from_job(job: Any) -> str:
    if isinstance(job, dict):
        value = job.get("cursor_key", "")
    else:
        value = getattr(job, "cursor_key", "")
    if not value:
        raise ValueError("scrivener job missing cursor_key")
    return str(value)


def process_scrivener_job(job: Any, *, writer_for_job) -> str:
    """Execute job, save outcome, and return cursor to orchestrator."""
    outcome_key = ScrivenerExecutor(writer_for_job).execute(job)
    enqueue_orchestrator(cursor_key_from_job(job))
    return outcome_key
