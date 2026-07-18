"""Ledger table and Redis-model contracts."""

CALLS_TABLE = "calls"
RESPONSES_TABLE = "responses"
EXPORTS_TABLE = "exports"

TABLE_BY_KEY_KIND = {
    # This pass intentionally implements initiation only. Response and export
    # persistence will be added when those artifact models are finalized.
    "call": CALLS_TABLE,
}

MODEL_PATH_BY_KEY_KIND = {
    "call": "asc.models.process.call.CallRecord",
}

LEDGER_FIELDS: dict[str, tuple[str, ...]] = {
    CALLS_TABLE: (
        "identity",
        "source_identity",
        "plan_key",
        "content",
        "created_at",
        "blob_json",
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

__all__ = [
    "CALLS_TABLE",
    "EXPORTS_TABLE",
    "LEDGER_FIELDS",
    "MODEL_PATH_BY_KEY_KIND",
    "RESPONSES_TABLE",
    "TABLE_BY_KEY_KIND",
]
