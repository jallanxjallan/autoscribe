use autoscribe_service::{
    Service,
    db::{self, Database},
    dispatch,
    types::{DispatchId, DispatchSource, PlanId, PrepareSavedDispatchRequest},
};
use serde::{Deserialize, Serialize};
use std::{
    env,
    io::{self, Read},
    path::PathBuf,
    process::ExitCode,
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct DispatchPrepareInput {
    version: u32,
    database_path: PathBuf,
    repository_path: PathBuf,
    dispatch: String,
    plan: String,
    plan_version: String,
    records: Vec<DispatchSourceInput>,
    payload: String,
    payload_sha256: String,
    commit_message: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct DispatchSourceInput {
    slug: String,
    path: PathBuf,
}

#[derive(Serialize)]
struct DispatchPrepareOutput {
    ok: bool,
    operation: &'static str,
    dispatch: String,
    source_revision: String,
    source_branch: String,
    branch: String,
    dispatch_commit: String,
    payload_sha256: String,
    committed_paths: Vec<PathBuf>,
}

#[derive(Serialize)]
struct ErrorOutput {
    ok: bool,
    operation: &'static str,
    error: String,
}

fn main() -> ExitCode {
    if env::args().nth(1).as_deref() == Some("dispatch-prepare") {
        return dispatch_prepare();
    }
    let config = env::args_os()
        .nth(1)
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("autoscribe-service.toml"));
    match Service::start(&config) {
        Ok(_) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("autoscribe-service: {error}");
            ExitCode::FAILURE
        }
    }
}

fn dispatch_prepare() -> ExitCode {
    match prepare_from_stdin() {
        Ok(output) => {
            println!(
                "{}",
                serde_json::to_string(&output).expect("serializable dispatch output")
            );
            ExitCode::SUCCESS
        }
        Err(error) => {
            let output = ErrorOutput {
                ok: false,
                operation: "dispatch.prepare",
                error: error.to_string(),
            };
            println!(
                "{}",
                serde_json::to_string(&output).expect("serializable error output")
            );
            ExitCode::FAILURE
        }
    }
}

fn prepare_from_stdin() -> Result<DispatchPrepareOutput, Box<dyn std::error::Error>> {
    let mut raw = String::new();
    io::stdin().read_to_string(&mut raw)?;
    let input: DispatchPrepareInput = serde_json::from_str(&raw)?;
    if input.version != 1 {
        return Err(format!("unsupported dispatch request version: {}", input.version).into());
    }
    if let Some(parent) = input.database_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let db = Database::open_path(&input.database_path)?;
    db::migrate(&db)?;
    let prepared = dispatch::prepare(
        &db,
        &input.repository_path,
        PrepareSavedDispatchRequest {
            dispatch: DispatchId(input.dispatch),
            plan: PlanId(input.plan),
            plan_version: input.plan_version,
            records: input
                .records
                .into_iter()
                .map(|record| DispatchSource {
                    slug: record.slug,
                    path: record.path,
                })
                .collect(),
            payload: input.payload.into_bytes(),
            payload_sha256: input.payload_sha256,
            commit_message: input.commit_message,
        },
    )?;
    Ok(DispatchPrepareOutput {
        ok: true,
        operation: "dispatch.prepare",
        dispatch: prepared.dispatch.0,
        source_revision: prepared.source_revision.0,
        source_branch: prepared.source_branch,
        branch: prepared.branch.name,
        dispatch_commit: prepared.branch.commit.0,
        payload_sha256: prepared.payload_sha256,
        committed_paths: prepared.committed_paths,
    })
}
