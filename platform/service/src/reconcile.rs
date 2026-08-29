use crate::{dispatch::sha256_hex, error::stub, types::*, ServiceResult};
use serde_json::Value;

pub fn run(_request: ReconcileRequest) -> ServiceResult<ReconcileReport> { stub("reconcile.run") }
pub fn apply(_decision: ReconcileDecision) -> ServiceResult<ReconcileReport> { stub("reconcile.apply") }

#[derive(Debug, Clone, PartialEq)]
pub struct AuthoredCatalogUpload {
    pub instructions: Vec<Value>,
    pub plans: Vec<Value>,
}

/// Select durable authored records that are absent or outdated in a live
/// server snapshot. Execution and scheduling remain the caller's concern.
pub fn authored_catalog(
    server: &Value,
    local_instructions: Vec<Value>,
    local_plans: Vec<Value>,
) -> AuthoredCatalogUpload {
    let registries = server.get("registries").unwrap_or(&Value::Null);
    let live_instructions = registries.get("instructions").and_then(Value::as_object);
    let live_plans = registries.get("plans").and_then(Value::as_object);

    let instructions = local_instructions.into_iter().filter(|record| {
        let Some(identity) = record.get("identity").and_then(Value::as_str) else { return true; };
        let local_hash = record.get("content").and_then(Value::as_str)
            .map(|content| sha256_hex(content.trim().as_bytes()));
        let remote_hash = live_instructions.and_then(|items| items.get(identity))
            .and_then(|item| item.get("content_sha256")).and_then(Value::as_str);
        local_hash.as_deref() != remote_hash
    }).collect();

    let plans = local_plans.into_iter().filter(|record| {
        let identity = record.get("record_identity").and_then(Value::as_str).unwrap_or("");
        let local_version = record.get("payload").and_then(|payload| {
            serde_json::to_vec(payload).ok().map(|bytes| {
                let mut versioned = identity.as_bytes().to_vec();
                versioned.push(0);
                versioned.extend(bytes);
                sha256_hex(&versioned)
            })
        });
        let remote_version = live_plans.and_then(|items| items.get(identity))
            .and_then(|item| item.get("identity")).and_then(Value::as_str);
        identity.is_empty() || local_version.as_deref() != remote_version
    }).map(|record| {
        let identity = record.get("record_identity").cloned().unwrap_or(Value::Null);
        let content = record.get("payload").cloned().unwrap_or(Value::Null);
        serde_json::json!({"type":"plan", "identity":identity, "content":content, "extra":{}})
    }).collect();

    AuthoredCatalogUpload { instructions, plans }
}
