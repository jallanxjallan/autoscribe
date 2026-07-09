"""Ledger table, action, and runtime-model contracts."""

from __future__ import annotations


CALLS_TABLE = "calls"
RESPONSES_TABLE = "responses"
EXPORTS_TABLE = "exports"

WRITE_CALL_ACTION = "write_call"
CALL_COMPLETED_ACTION = "call_completed"
CALL_FAILED_ACTION = "call_failed"
CONFIRM_EXPORT_ACTION = "confirm_export"

ACTION_TABLES = {
    WRITE_CALL_ACTION: CALLS_TABLE,
    CALL_COMPLETED_ACTION: RESPONSES_TABLE,
    CALL_FAILED_ACTION: RESPONSES_TABLE,
    CONFIRM_EXPORT_ACTION: EXPORTS_TABLE,
}

LEDGER_FIELDS: dict[str, tuple[str, ...]] = {
    CALLS_TABLE: (
        "identity",
        "source_identity",
        "source_json",
        "created_at",
    ),
    RESPONSES_TABLE: (
        "identity",
        "final_step",
        "result_key",
        "result_kind",
        "status",
        "content",
        "fail_message",
        "raw_json",
        "created_at",
    ),
    EXPORTS_TABLE: (
        "response_identity",
        "destination",
        "export_mode",
        "target_slug",
        "target_path",
        "exported_at",
        "export_message",
        "consumer_json",
        "created_at",
    ),
}

MODEL_PATH_BY_KEY_KIND = {
    "call": "asc.models.process.call.CallRecord",
    "response": "asc.models.process.result.Response",
    "transform": "asc.models.process.result.Transform",
    "retrieval": "asc.models.process.result.Retrieval",
    "result": "asc.models.process.result.Result",
    "failure": "asc.models.process.result.Failure",
}

SUCCESS_RESULT_KINDS = frozenset({"response", "transform", "retrieval", "result"})
FAILURE_RESULT_KIND = "failure"
RESULT_KINDS = frozenset({*SUCCESS_RESULT_KINDS, FAILURE_RESULT_KIND})

__all__ = [
    "ACTION_TABLES",
    "CALL_COMPLETED_ACTION",
    "CALL_FAILED_ACTION",
    "CALLS_TABLE",
    "CONFIRM_EXPORT_ACTION",
    "EXPORTS_TABLE",
    "FAILURE_RESULT_KIND",
    "LEDGER_FIELDS",
    "MODEL_PATH_BY_KEY_KIND",
    "RESPONSES_TABLE",
    "RESULT_KINDS",
    "SUCCESS_RESULT_KINDS",
    "WRITE_CALL_ACTION",
]
