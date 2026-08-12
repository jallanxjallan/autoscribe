from dataclasses import dataclass
import json
from typing import Any
from asc.ledger.connect import connect
TABLE_NAMES=("calls","results","exports")
@dataclass(frozen=True,slots=True)
class TableCount: table:str; rows:int
def _row(row): return {} if row is None else {k:row[k] for k in row.keys()}
def _json(v):
    if not isinstance(v,str) or not v:return None
    try:return json.loads(v)
    except Exception:return v
def table_counts():
    with connect() as conn:return tuple(TableCount(t,int(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])) for t in TABLE_NAMES)
def recent_calls(*,limit=20):
    with connect() as conn:
        rows=conn.execute("""SELECT c.identity,c.source_identity,c.created_at,r.status AS result_status,r.final_step,r.result_key,r.result_kind,r.created_at AS result_created_at,COUNT(e.export_id) AS exports FROM calls c LEFT JOIN results r ON r.identity=c.identity LEFT JOIN exports e ON e.result_identity=c.identity GROUP BY c.identity ORDER BY c.created_at DESC LIMIT ?""",(limit,)).fetchall()
    return [_row(x) for x in rows]
def recent_results(*,limit=50,statuses=()):
    where=""; params=[]
    if statuses: where=f"WHERE r.status IN ({','.join('?' for _ in statuses)})"; params.extend(statuses)
    params.append(limit)
    with connect() as conn: rows=conn.execute(f"SELECT r.*,c.source_identity FROM results r JOIN calls c ON c.identity=r.identity {where} ORDER BY r.created_at DESC,r.identity LIMIT ?",tuple(params)).fetchall()
    return [_row(x) for x in rows]
def recent_exports(*,limit=30):
    with connect() as conn: rows=conn.execute("SELECT e.*,c.source_identity FROM exports e JOIN calls c ON c.identity=e.result_identity ORDER BY e.created_at DESC LIMIT ?",(limit,)).fetchall()
    return [_row(x) for x in rows]
def pending_exports(*,limit=50):
    with connect() as conn: rows=conn.execute("""SELECT c.source_identity AS record_identity,r.identity AS call_identity,r.final_step,r.result_key,r.result_kind,r.created_at FROM results r JOIN calls c ON c.identity=r.identity LEFT JOIN exports e ON e.result_identity=r.identity WHERE r.status='success' AND e.result_identity IS NULL ORDER BY r.created_at LIMIT ?""",(limit,)).fetchall()
    return [_row(x) for x in rows]
def pending_export_for_source(source_identity):
    with connect() as conn: row=conn.execute("""SELECT c.source_identity AS record_identity,r.identity AS call_identity,r.final_step,r.result_key,r.result_kind,r.created_at FROM results r JOIN calls c ON c.identity=r.identity LEFT JOIN exports e ON e.result_identity=r.identity WHERE c.source_identity=? AND r.status='success' AND e.result_identity IS NULL ORDER BY r.created_at LIMIT 1""",(source_identity,)).fetchone()
    return _row(row) if row else None
def pending_work(*,limit=50):
    failed=recent_results(limit=limit,statuses=("failure",))
    exports=pending_exports(limit=max(0,limit-len(failed)))
    for row in exports: row.setdefault("status","pending_export")
    return (failed+exports)[:limit]
def show_call(identity):
    with connect() as conn:
        call=conn.execute("SELECT * FROM calls WHERE identity=?",(identity,)).fetchone()
        if call is None: raise KeyError(f"call not found: {identity}")
        result=conn.execute("SELECT * FROM results WHERE identity=?",(identity,)).fetchone()
        exports=conn.execute("SELECT * FROM exports WHERE result_identity=? ORDER BY exported_at,export_id",(identity,)).fetchall()
    return {"call":_row(call),"source":_json(call["extra_json"]),"result":_row(result) if result else None,"exports":[_row(x) for x in exports]}
def show_result(identity):
    with connect() as conn: row=conn.execute("SELECT * FROM results WHERE identity=?",(identity,)).fetchone()
    if row is None: raise KeyError(f"result not found: {identity}")
    data=_row(row); data["raw"]=_json(data.get("raw_json")); return data
__all__=["TableCount","table_counts","recent_calls","recent_results","recent_exports","pending_exports","pending_export_for_source","pending_work","show_call","show_result"]
