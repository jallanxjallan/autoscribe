PENDING_EXPORTS_VIEW="pending_exports"
CREATE_PENDING_EXPORTS_VIEW_SQL=f"""CREATE VIEW IF NOT EXISTS {PENDING_EXPORTS_VIEW} AS SELECT c.source_identity AS record_identity, c.identity AS call_identity, r.final_step, r.result_key, r.result_kind, r.content, r.raw_json, r.created_at FROM results r JOIN calls c ON c.identity=r.identity LEFT JOIN exports e ON e.result_identity=r.identity WHERE r.status='success' AND e.result_identity IS NULL"""
SELECT_PENDING_EXPORTS_SQL=f"SELECT record_identity, call_identity, final_step, result_key, result_kind, content, raw_json, created_at FROM {PENDING_EXPORTS_VIEW} ORDER BY record_identity, call_identity"
SELECT_DUPLICATE_PENDING_EXPORT_SLUGS_SQL=f"SELECT record_identity, COUNT(*) pending_count FROM {PENDING_EXPORTS_VIEW} GROUP BY record_identity HAVING COUNT(*)>1 ORDER BY record_identity"
SELECT_DUPLICATE_PENDING_EXPORT_ROWS_SQL=f"SELECT p.record_identity,p.call_identity,p.final_step,p.result_key FROM {PENDING_EXPORTS_VIEW} p JOIN (SELECT record_identity FROM {PENDING_EXPORTS_VIEW} GROUP BY record_identity HAVING COUNT(*)>1) d ON d.record_identity=p.record_identity ORDER BY p.record_identity,p.call_identity"
LEDGER_VIEW_NAMES=(PENDING_EXPORTS_VIEW,)
CREATE_LEDGER_VIEWS_SQL=(CREATE_PENDING_EXPORTS_VIEW_SQL,)
