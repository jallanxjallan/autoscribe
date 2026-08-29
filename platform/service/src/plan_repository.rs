use crate::{ServiceError, ServiceResult, git};
use serde_json::Value;
use std::{collections::BTreeSet, path::Path};

pub fn list(repo: &Path) -> ServiceResult<Vec<Value>> {
    let mut records = git::config_list_json(repo, "plans")?;
    records.sort_by(|a, b| identity_value(a).cmp(&identity_value(b)));
    Ok(records)
}

pub fn list_at(repo: &Path, revision: &str) -> ServiceResult<Vec<Value>> {
    let mut records = git::config_list_json_at(repo, "plans", revision)?;
    records.sort_by(|a, b| identity_value(a).cmp(&identity_value(b)));
    Ok(records)
}

pub fn save(repo: &Path, plan: &Value) -> ServiceResult<String> {
    let plan_identity = validate(plan)?;
    let commit = git::config_upsert_json(
        repo,
        "plans",
        plan_identity,
        plan,
        &format!("AUTOSCRIBE CONFIG plan {plan_identity}"),
    )?;
    Ok(commit.0)
}

pub fn validate(plan: &Value) -> ServiceResult<&str> {
    let plan_identity = identity(plan, "record_identity")?;
    let payload = plan.get("payload").and_then(Value::as_object).ok_or_else(|| {
        ServiceError::InvalidInput(format!("{plan_identity}: plan payload must be an object"))
    })?;
    if payload.get("steps").and_then(Value::as_object).is_none_or(|steps| steps.is_empty()) {
        return Err(ServiceError::InvalidInput(format!("{plan_identity}: plan requires steps")));
    }
    Ok(plan_identity)
}



/// Validate the fields that a Plan Manager is allowed to persist against the
/// catalog visible at the captured config revision. This is the daemon-side
/// acceptance gate: even if another frontend writes malformed JSON directly
/// to the config ref, it will never be uploaded to the pipeline.
pub fn validate_against_catalog(plan: &Value, catalogs: &Value) -> ServiceResult<()> {
    let plan_identity = validate(plan)?;
    if let Some(record_type) = plan.get("record_type").and_then(Value::as_str) {
        if record_type != "plan" {
            return Err(ServiceError::InvalidInput(format!(
                "{plan_identity}: record_type must be plan"
            )));
        }
    }

    let engines = catalog_identities(catalogs, "engines");
    let models = catalog_identities(catalogs, "models");
    let scripts = catalog_identities(catalogs, "scripts");
    let rag_profiles = catalog_identities(catalogs, "rag_profiles");
    let instructions = catalog_identities(catalogs, "instructions");
    let steps = plan["payload"]["steps"].as_object().expect("validate checked steps");
    let mut ordered_steps = steps.iter().map(|(key, step)| {
        key.parse::<usize>().map(|number| (number, key.as_str(), step)).map_err(|_| {
            ServiceError::InvalidInput(format!(
                "{plan_identity}: step key must be a positive integer: {key}"
            ))
        })
    }).collect::<ServiceResult<Vec<_>>>()?;
    ordered_steps.sort_by_key(|(number, _, _)| *number);

    let mut expected = 1usize;
    for (number, _key, step) in ordered_steps {
        if number != expected {
            return Err(ServiceError::InvalidInput(format!(
                "{plan_identity}: steps must be sequential starting at 1 (expected {expected}, found {number})"
            )));
        }
        expected += 1;
        let object = step.as_object().ok_or_else(|| ServiceError::InvalidInput(format!(
            "{plan_identity}: step {number} must be an object"
        )))?;
        if let Some(index) = object.get("index").and_then(Value::as_u64) {
            if index != number as u64 {
                return Err(ServiceError::InvalidInput(format!(
                    "{plan_identity}: step {number} index must equal its step number"
                )));
            }
        }
        if let Some(args) = object.get("args") {
            if !args.is_object() {
                return Err(ServiceError::InvalidInput(format!(
                    "{plan_identity}: step {number} args must be an object"
                )));
            }
        }

        validate_instruction_refs(plan_identity, number, object.get("instruction_slugs"), &instructions)?;
        let kind = object.get("kind").and_then(Value::as_str).unwrap_or("").trim();
        match kind {
            "llm" => {
                require_catalog_member(plan_identity, number, "engine", object.get("engine"), &engines)?;
                require_catalog_member(plan_identity, number, "model", object.get("model"), &models)?;
                validate_model_owner(plan_identity, number, object, catalogs)?;
            }
            "script" => {
                require_catalog_member(plan_identity, number, "script", object.get("script"), &scripts)?;
                optional_catalog_member(plan_identity, number, "engine", object.get("engine"), &engines)?;
            }
            "rag" => {
                require_catalog_member(plan_identity, number, "rag_profile", object.get("rag_profile"), &rag_profiles)?;
                optional_catalog_member(plan_identity, number, "engine", object.get("engine"), &engines)?;
            }
            _ => {
                return Err(ServiceError::InvalidInput(format!(
                    "{plan_identity}: step {number} kind must be llm, script, or rag"
                )));
            }
        }
    }
    Ok(())
}

fn validate_instruction_refs(
    plan_identity: &str,
    step: usize,
    value: Option<&Value>,
    available: &BTreeSet<String>,
) -> ServiceResult<()> {
    let Some(value) = value else { return Ok(()); };
    let refs = value.as_object().ok_or_else(|| ServiceError::InvalidInput(format!(
        "{plan_identity}: step {step} instruction_slugs must be an object"
    )))?;
    for (component, entries) in refs {
        if !matches!(component.as_str(), "standing" | "role" | "context" | "task") {
            return Err(ServiceError::InvalidInput(format!(
                "{plan_identity}: step {step} has unsupported instruction component: {component}"
            )));
        }
        let entries = entries.as_array().ok_or_else(|| ServiceError::InvalidInput(format!(
            "{plan_identity}: step {step} instruction_slugs.{component} must be an array"
        )))?;
        if component != "standing" && entries.len() > 1 {
            return Err(ServiceError::InvalidInput(format!(
                "{plan_identity}: step {step} instruction_slugs.{component} accepts at most one instruction"
            )));
        }
        for entry in entries {
            let slug = entry.as_str().unwrap_or("").trim();
            if slug.is_empty() || !available.contains(slug) {
                return Err(ServiceError::InvalidInput(format!(
                    "{plan_identity}: step {step} references unavailable instruction: {slug}"
                )));
            }
        }
    }
    Ok(())
}

fn require_catalog_member(
    plan_identity: &str,
    step: usize,
    field: &str,
    value: Option<&Value>,
    available: &BTreeSet<String>,
) -> ServiceResult<()> {
    let selected = value.and_then(Value::as_str).unwrap_or("").trim();
    if selected.is_empty() {
        return Err(ServiceError::InvalidInput(format!(
            "{plan_identity}: step {step} requires {field}"
        )));
    }
    if !available.contains(selected) {
        return Err(ServiceError::InvalidInput(format!(
            "{plan_identity}: step {step} references unavailable {field}: {selected}"
        )));
    }
    Ok(())
}

fn optional_catalog_member(
    plan_identity: &str,
    step: usize,
    field: &str,
    value: Option<&Value>,
    available: &BTreeSet<String>,
) -> ServiceResult<()> {
    let selected = value.and_then(Value::as_str).unwrap_or("").trim();
    if selected.is_empty() { return Ok(()); }
    if !available.contains(selected) {
        return Err(ServiceError::InvalidInput(format!(
            "{plan_identity}: step {step} references unavailable {field}: {selected}"
        )));
    }
    Ok(())
}


fn validate_model_owner(
    plan_identity: &str,
    step: usize,
    object: &serde_json::Map<String, Value>,
    catalogs: &Value,
) -> ServiceResult<()> {
    let engine = object.get("engine").and_then(Value::as_str).unwrap_or("").trim();
    let model = object.get("model").and_then(Value::as_str).unwrap_or("").trim();
    let owner = catalogs.get("models").and_then(Value::as_array).into_iter().flatten()
        .find(|record| record_identity(record) == model)
        .and_then(|record| ["engine", "engine_key", "provider", "provider_key"].into_iter()
            .find_map(|field| record.get(field).and_then(Value::as_str)))
        .unwrap_or("").trim();
    if !owner.is_empty() && owner != engine {
        return Err(ServiceError::InvalidInput(format!(
            "{plan_identity}: step {step} model {model} does not belong to engine {engine}"
        )));
    }
    Ok(())
}

fn record_identity(record: &Value) -> &str {
    ["record_identity", "identity", "slug", "key", "name"]
        .into_iter()
        .find_map(|field| record.get(field).and_then(Value::as_str))
        .unwrap_or("")
        .trim()
}

fn catalog_identities(catalogs: &Value, name: &str) -> BTreeSet<String> {
    catalogs.get(name).and_then(Value::as_array).into_iter().flatten().filter_map(|record| {
        let value = record_identity(record);
        (!value.is_empty()).then(|| value.to_string())
    }).collect()
}

fn identity_value(record: &Value) -> String {
    record.get("record_identity").and_then(Value::as_str).unwrap_or("").to_string()
}

fn identity<'a>(record: &'a Value, field: &str) -> ServiceResult<&'a str> {
    let value = record.get(field).and_then(Value::as_str).unwrap_or("").trim();
    if value.is_empty() {
        Err(ServiceError::InvalidInput(format!("record requires {field}")))
    } else {
        Ok(value)
    }
}
