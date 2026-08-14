use crate::{ServiceError, ServiceResult, db::Database, dispatch::sha256_hex};
use serde_json::Value;

pub fn list(db: &Database, table: &str) -> ServiceResult<Vec<Value>> {
    let sql = match table {
        "instructions" => {
            "SELECT record_json FROM authored_instructions ORDER BY instruction_identity"
        }
        "plans" => "SELECT record_json FROM authored_plans ORDER BY plan_identity",
        _ => {
            return Err(ServiceError::InvalidInput(format!(
                "unknown authored record table: {table}"
            )));
        }
    };
    let mut statement = db.connection().prepare(sql).map_err(storage)?;
    let rows = statement
        .query_map([], |row| row.get::<_, String>(0))
        .map_err(storage)?;
    rows.map(|row| {
        let text = row.map_err(storage)?;
        serde_json::from_str(&text).map_err(|error| ServiceError::Storage(error.to_string()))
    })
    .collect()
}

pub fn save(db: &Database, plan: &Value, instructions: &[Value]) -> ServiceResult<()> {
    let plan_identity = identity(plan, "record_identity")?;
    let payload = plan
        .get("payload")
        .and_then(Value::as_object)
        .ok_or_else(|| {
            ServiceError::InvalidInput(format!("{plan_identity}: plan payload must be an object"))
        })?;
    if payload
        .get("steps")
        .and_then(Value::as_object)
        .is_none_or(|steps| steps.is_empty())
    {
        return Err(ServiceError::InvalidInput(format!(
            "{plan_identity}: plan requires steps"
        )));
    }
    let transaction = db.connection().unchecked_transaction().map_err(storage)?;
    for instruction in instructions {
        let identity = identity(instruction, "identity")?;
        let content = instruction
            .get("content")
            .and_then(Value::as_str)
            .unwrap_or("");
        if content.trim().is_empty() {
            return Err(ServiceError::InvalidInput(format!(
                "{identity}: instruction content is blank"
            )));
        }
        transaction.execute(
            "INSERT INTO authored_instructions (instruction_identity, record_json, content_sha256)
             VALUES (?1, ?2, ?3)
             ON CONFLICT(instruction_identity) DO UPDATE SET
               record_json=excluded.record_json, content_sha256=excluded.content_sha256,
               updated_at=CURRENT_TIMESTAMP",
            (identity, serde_json::to_string(instruction).map_err(json)?, sha256_hex(content.as_bytes())),
        ).map_err(storage)?;
    }
    transaction.execute(
        "INSERT INTO authored_plans (plan_identity, record_json) VALUES (?1, ?2)
         ON CONFLICT(plan_identity) DO UPDATE SET record_json=excluded.record_json, updated_at=CURRENT_TIMESTAMP",
        (plan_identity, serde_json::to_string(plan).map_err(json)?),
    ).map_err(storage)?;
    transaction.commit().map_err(storage)
}

fn identity<'a>(record: &'a Value, field: &str) -> ServiceResult<&'a str> {
    let value = record
        .get(field)
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim();
    if value.is_empty() {
        Err(ServiceError::InvalidInput(format!(
            "record requires {field}"
        )))
    } else {
        Ok(value)
    }
}
fn storage(error: rusqlite::Error) -> ServiceError {
    ServiceError::Storage(error.to_string())
}
fn json(error: serde_json::Error) -> ServiceError {
    ServiceError::InvalidInput(error.to_string())
}
