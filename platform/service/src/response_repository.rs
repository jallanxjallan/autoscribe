use crate::{ServiceError, ServiceResult, db::Database};
use serde_json::Value;

pub fn store_pending(db: &Database, records: &[Value]) -> ServiceResult<()> {
    let transaction = db.connection().unchecked_transaction().map_err(storage)?;
    for record in records {
        let result = required(record, "result_identity")?;
        let source = required(record, "source_identity")?;
        let call = required(record, "call_identity")?;
        let lineage = transaction.query_row(
            "SELECT d.dispatch_identity, d.ledger_commit, s.blob_hash
             FROM inflight_sources s JOIN inflight_dispatches d USING(dispatch_identity)
             WHERE s.source_slug=?1 ORDER BY d.created_at DESC, d.rowid DESC LIMIT 1",
            [source], |row| Ok((row.get::<_,String>(0)?, row.get::<_,String>(1)?, row.get::<_,String>(2)?)),
        ).map_err(|_| ServiceError::Conflict(format!("no inflight ledger source for response: {source}")))?;
        transaction.execute(
            "INSERT INTO response_records
             (result_identity,source_identity,call_identity,dispatch_identity,ledger_commit,source_blob,record_json,state)
             VALUES (?1,?2,?3,?4,?5,?6,?7,'pending')
             ON CONFLICT(result_identity) DO UPDATE SET record_json=excluded.record_json,
               updated_at=CURRENT_TIMESTAMP WHERE response_records.state='pending'",
            (result,source,call,lineage.0,lineage.1,lineage.2,serde_json::to_string(record).map_err(json)?),
        ).map_err(storage)?;
    }
    transaction.commit().map_err(storage)
}

pub fn pending(db: &Database) -> ServiceResult<Vec<Value>> {
    let mut statement=db.connection().prepare(
        "SELECT r.record_json,r.dispatch_identity,r.ledger_commit,r.source_blob,s.source_path
         FROM response_records r
         JOIN inflight_sources s ON s.dispatch_identity=r.dispatch_identity AND s.source_slug=r.source_identity
         WHERE r.state IN ('pending','written') ORDER BY r.updated_at,r.result_identity").map_err(storage)?;
    let rows=statement.query_map([],|row|Ok((row.get::<_,String>(0)?,row.get::<_,String>(1)?,row.get::<_,String>(2)?,row.get::<_,String>(3)?,row.get::<_,String>(4)?))).map_err(storage)?;
    rows.map(|row|{let (raw,dispatch,commit,blob,path)=row.map_err(storage)?;let mut value:Value=serde_json::from_str(&raw).map_err(json)?;
        value["dispatch_identity"]=dispatch.into();value["ledger_commit"]=commit.into();value["source_blob"]=blob.into();value["source_path"]=path.into();Ok(value)}).collect()
}

pub fn require_pending(db:&Database,result:&str,source:&str)->ServiceResult<(String,String,String,String,Option<String>,Option<String>,Option<String>,Option<String>)> {
    db.connection().query_row(
        "SELECT state,dispatch_identity,ledger_commit,source_blob,intended_outcome,source_path,writeback_commit,forensic_commit FROM response_records
         WHERE result_identity=?1 AND source_identity=?2 AND state IN ('pending','written')",(result,source),
        |row|Ok((row.get(0)?,row.get(1)?,row.get(2)?,row.get(3)?,row.get(4)?,row.get(5)?,row.get(6)?,row.get(7)?)),
    ).map_err(|_|ServiceError::Conflict(format!("pending response not found: {result}")))
}

pub fn mark_written(db:&Database,result:&str,outcome:&str,path:Option<&str>,commit:Option<&str>)->ServiceResult<()> {
    let changed=db.connection().execute(
        "UPDATE response_records SET state='written',intended_outcome=?2,source_path=?3,writeback_commit=?4,updated_at=CURRENT_TIMESTAMP
         WHERE result_identity=?1 AND state='pending'",(result,outcome,path,commit)).map_err(storage)?;
    if changed==1{Ok(())}else{Err(ServiceError::Conflict(format!("response is not pending: {result}")))}
}

pub fn mark_forensic(db:&Database,result:&str,commit:&str)->ServiceResult<()> {
    let changed=db.connection().execute(
        "UPDATE response_records SET forensic_commit=?2,updated_at=CURRENT_TIMESTAMP
         WHERE result_identity=?1 AND state IN ('pending','written')",(result,commit)).map_err(storage)?;
    if changed==1{Ok(())}else{Err(ServiceError::Conflict(format!("response is not pending or written: {result}")))}
}
pub fn complete(db:&Database,result:&str)->ServiceResult<()> {
    let changed=db.connection().execute("DELETE FROM response_records WHERE result_identity=?1 AND state='written'",[result]).map_err(storage)?;
    if changed==1{Ok(())}else{Err(ServiceError::Conflict(format!("response is not awaiting completion: {result}")))}
}
fn required<'a>(record:&'a Value,field:&str)->ServiceResult<&'a str>{record.get(field).and_then(Value::as_str).map(str::trim).filter(|v|!v.is_empty()).ok_or_else(||ServiceError::InvalidInput(format!("response requires {field}")))}
fn storage(error:rusqlite::Error)->ServiceError{ServiceError::Storage(error.to_string())}
fn json(error:serde_json::Error)->ServiceError{ServiceError::InvalidInput(error.to_string())}
