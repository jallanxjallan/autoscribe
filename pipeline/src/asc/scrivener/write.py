"""Compatibility wrapper for Scrivener ledger writes.

The write implementation lives in asc.scrivener.execute so the daemon and any
legacy direct callers use the same table/action contract.
"""

from asc.scrivener.execute import write_task, write_task_with_connection
from asc.scrivener.maps import (
    CALL_ACTION,
    CONFIRM_EXPORT_ACTION,
    EXPORT_ACTION,
    STEP_ACTION,
)


__all__ = [
    "CALL_ACTION",
    "CONFIRM_EXPORT_ACTION",
    "EXPORT_ACTION",
    "STEP_ACTION",
    "write_task",
    "write_task_with_connection",
]
