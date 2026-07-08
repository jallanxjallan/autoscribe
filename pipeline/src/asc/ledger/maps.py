"""Scrivener table/action/model maps and exact row shapes."""

from __future__ import annotations


CALLS_TABLE = "calls"
STEPS_TABLE = "steps"
EXPORTS_TABLE = "exports"

CALL_ACTION = "write_call"
STEP_ACTION = "write_step"
EXPORT_ACTION = "call_completed"
CONFIRM_EXPORT_ACTION = "confirm_export"

ACTION_TABLES = {
    CALL_ACTION: CALLS_TABLE,
    STEP_ACTION: STEPS_TABLE,
    EXPORT_ACTION: EXPORTS_TABLE,
}

LEDGER_FIELDS: dict[str, tuple[str, ...]] = {
    CALLS_TABLE: (
        "identity",
        "source_identity",
        "source_json",
        "created_at",
    ),
    STEPS_TABLE: (
        "identity",
        "step_number",
        "result_key",
        "status",
        "content",
        "fail_message",
        "raw_json",
        "created_at",
    ),
    EXPORTS_TABLE: (
        "identity",
        "source_identity",
        "final_step",
        "result_key",
        "exported_at",
        "export_message",
        "created_at",
    ),
}

MODEL_PATH_BY_KEY_KIND = {
    "call": "asc.models.process.call.CallRecord",
    "response": "asc.models.process.result.Response",
    "transform": "asc.models.process.result.Transform",
    "retrieval": "asc.models.process.result.Retrieval",
    "failure": "asc.models.process.result.Failure",
}

__all__ = [
    "ACTION_TABLES",
    "CALL_ACTION",
    "CALLS_TABLE",
    "CONFIRM_EXPORT_ACTION",
    "EXPORT_ACTION",
    "EXPORTS_TABLE",
    "LEDGER_FIELDS",
    "MODEL_PATH_BY_KEY_KIND",
    "STEP_ACTION",
    "STEPS_TABLE",
]
