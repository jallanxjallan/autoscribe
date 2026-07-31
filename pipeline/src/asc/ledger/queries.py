from asc.ledger.util import insert_sql

CALL_COLUMNS=("identity","source_identity","content","created_at","extra_json")
RESULT_COLUMNS=("identity","final_step","result_key","result_kind","status","content","fail_message","raw_json","created_at")
EXPORT_COLUMNS=("result_identity","destination","export_mode","target_slug","target_path","exported_at","export_message","consumer_json","created_at")
INSERT_CALL_SQL=insert_sql("calls",CALL_COLUMNS)
INSERT_RESULT_SQL=insert_sql("results",RESULT_COLUMNS)
INSERT_EXPORT_SQL=insert_sql("exports",EXPORT_COLUMNS)
SELECT_CALL_SQL=f"SELECT {', '.join(CALL_COLUMNS)} FROM calls WHERE identity = ?"
SELECT_CALL_BY_SOURCE_IDENTITY_SQL=f"SELECT {', '.join(CALL_COLUMNS)} FROM calls WHERE source_identity = ? ORDER BY created_at DESC LIMIT 1"
SELECT_CALLS_SQL=f"SELECT {', '.join(CALL_COLUMNS)} FROM calls ORDER BY created_at ASC"
SELECT_RESULT_SQL=f"SELECT {', '.join(RESULT_COLUMNS)} FROM results WHERE identity = ?"
SELECT_RESULTS_SQL=f"SELECT {', '.join(RESULT_COLUMNS)} FROM results ORDER BY created_at ASC"
SELECT_EXPORT_BY_ID_SQL="SELECT export_id, result_identity, destination, export_mode, target_slug, target_path, exported_at, export_message, consumer_json, created_at FROM exports WHERE export_id = ?"
SELECT_EXPORTS_FOR_RESULT_SQL="SELECT export_id, result_identity, destination, export_mode, target_slug, target_path, exported_at, export_message, consumer_json, created_at FROM exports WHERE result_identity = ? ORDER BY exported_at ASC, export_id ASC"
SELECT_PENDING_EXPORTS_SQL="""SELECT c.source_identity AS record_identity, r.identity AS call_identity, r.final_step, r.result_key, r.result_kind, r.content, r.raw_json, r.created_at FROM results r JOIN calls c ON c.identity=r.identity LEFT JOIN exports e ON e.result_identity=r.identity WHERE r.status='success' AND e.result_identity IS NULL ORDER BY c.source_identity, r.identity"""
SELECT_PENDING_EXPORT_BY_SOURCE_IDENTITY_SQL=SELECT_PENDING_EXPORTS_SQL.replace(" ORDER BY", " AND c.source_identity = ? ORDER BY")+" LIMIT 1"
SELECT_EXTRACT_RESULT_BY_CALL_IDENTITY_SQL="""SELECT c.identity, c.source_identity, c.content AS source_content, c.extra_json, c.created_at AS call_created_at, r.final_step AS step_number, r.result_key, r.result_kind, r.content, r.raw_json, r.created_at AS step_created_at, e.created_at AS export_created_at, e.exported_at, e.export_message FROM calls c JOIN results r ON r.identity=c.identity LEFT JOIN exports e ON e.result_identity=r.identity WHERE c.identity=? ORDER BY e.exported_at DESC, e.export_id DESC LIMIT 1"""
__all__=[name for name in globals() if name.isupper()]
