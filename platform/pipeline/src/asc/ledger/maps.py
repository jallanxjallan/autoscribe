"""Ledger table and artifact contracts."""

CALLS_TABLE = "calls"
RESULTS_TABLE = "results"
EXPORTS_TABLE = "exports"

TABLE_BY_KEY_KIND = {"call": CALLS_TABLE}
MODEL_PATH_BY_KEY_KIND = {"call": "asc.models.process.call.CallRecord"}

LEDGER_FIELDS = {
    CALLS_TABLE: ("identity", "source_identity", "content", "created_at", "extra_json"),
    RESULTS_TABLE: ("identity", "final_step", "result_key", "result_kind", "status", "content", "fail_message", "raw_json", "created_at"),
    EXPORTS_TABLE: ("result_identity", "destination", "export_mode", "target_slug", "target_path", "exported_at", "export_message", "consumer_json", "created_at"),
}

__all__ = ["CALLS_TABLE", "RESULTS_TABLE", "EXPORTS_TABLE", "LEDGER_FIELDS", "TABLE_BY_KEY_KIND", "MODEL_PATH_BY_KEY_KIND"]
