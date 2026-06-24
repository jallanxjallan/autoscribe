"""Scrivener table names and exact row shapes."""

from __future__ import annotations


CALLS_TABLE = "calls"
STEPS_TABLE = "steps"
EXPORTS_TABLE = "exports"

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
    "result": "asc.models.process.result.Response",
    "failure": "asc.models.process.result.Failure",
}

STEP_STATUS_BY_KEY_KIND = {
    "response": "completed",
    "result": "completed",
    "failure": "failed",
}

__all__ = [
    "CALLS_TABLE",
    "EXPORTS_TABLE",
    "LEDGER_FIELDS",
    "MODEL_PATH_BY_KEY_KIND",
    "STEPS_TABLE",
    "STEP_STATUS_BY_KEY_KIND",
]
