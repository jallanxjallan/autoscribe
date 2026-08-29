use autoscribe_service::{ServiceError, plan_repository};
use serde_json::json;

fn catalogs() -> serde_json::Value {
    json!({
        "engines":[{"key":"chatgpt"}],
        "models":[{"key":"sol","engine":"chatgpt"}],
        "scripts":[{"key":"prose_tics"}],
        "rag_profiles":[{"key":"research.default"}],
        "instructions":[
            {"slug":"std.output"},
            {"slug":"rol.editor"},
            {"slug":"ctx.project"},
            {"slug":"tsk.rewrite"}
        ],
        "plans":[]
    })
}

#[test]
fn catalog_validation_accepts_restricted_plan_values() {
    let plan = json!({
        "record_type":"plan",
        "record_identity":"plan.valid",
        "payload":{"steps":{
            "1":{
                "index":1,
                "kind":"llm",
                "engine":"chatgpt",
                "model":"sol",
                "instruction_slugs":{
                    "standing":["std.output"],
                    "role":["rol.editor"],
                    "context":["ctx.project"],
                    "task":["tsk.rewrite"]
                }
            },
            "2":{"index":2,"kind":"script","script":"prose_tics"},
            "3":{"index":3,"kind":"rag","rag_profile":"research.default"}
        }}
    });
    plan_repository::validate_against_catalog(&plan, &catalogs()).unwrap();
}

#[test]
fn catalog_validation_rejects_unknown_plan_references() {
    let plan = json!({
        "record_type":"plan",
        "record_identity":"plan.invalid",
        "payload":{"steps":{
            "1":{
                "index":1,
                "kind":"llm",
                "engine":"chatgpt",
                "model":"does-not-exist",
                "instruction_slugs":{"task":["tsk.rewrite"]}
            }
        }}
    });
    assert!(matches!(
        plan_repository::validate_against_catalog(&plan, &catalogs()),
        Err(ServiceError::InvalidInput(message)) if message.contains("unavailable model")
    ));
}
