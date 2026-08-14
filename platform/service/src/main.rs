use autoscribe_service::{
    Service,
    db::{self, Database},
    dispatch,
    events::{self, NoticeSink},
    plan_repository,
    sync::{self, UploadOutcome},
    types::{DispatchId, DispatchSource, PlanId, PrepareSavedDispatchRequest},
};
use serde::{Deserialize, Serialize};
use std::{
    env,
    io::{self, Read},
    path::{Path, PathBuf},
    process::{Command, ExitCode, Stdio},
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

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct DispatchEnvelope {
    version: u32,
    calls: Vec<serde_json::Value>,
    enqueue: Vec<serde_json::Value>,
}

#[derive(Serialize)]
struct DispatchTransmitOutput {
    ok: bool,
    operation: &'static str,
    dispatch: String,
    state: &'static str,
    calls: usize,
    enqueue: usize,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PlanSaveInput {
    version: u32,
    database_path: PathBuf,
    plan: serde_json::Value,
    instructions: Vec<serde_json::Value>,
}

#[derive(Serialize)]
struct PlanSaveOutput {
    ok: bool,
    operation: &'static str,
    plan: String,
    instructions: usize,
}

#[derive(Serialize)]
struct DefinePlanSnapshotOutput {
    ok: bool,
    operation: &'static str,
    server: serde_json::Value,
    authored_plans: Vec<serde_json::Value>,
    authored_instructions: Vec<serde_json::Value>,
}

fn main() -> ExitCode {
    match env::args().nth(1).as_deref() {
        Some("dispatch-prepare") => return dispatch_prepare(),
        Some("dispatch-transmit") => return dispatch_transmit(),
        Some("define-plan-snapshot") => return define_plan_snapshot(),
        Some("plan-save") => return plan_save(),
        _ => {}
    }
    let config = env::args_os()
        .nth(1)
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("autoscribe-service.toml"));
    match Service::start(&config) {
        Ok(_) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("svc: {error}");
            ExitCode::FAILURE
        }
    }
}

fn define_plan_snapshot() -> ExitCode {
    command_output("define-plan.snapshot", snapshot_from_service())
}

fn snapshot_from_service() -> Result<DefinePlanSnapshotOutput, Box<dyn std::error::Error>> {
    let database_path = env::var_os("AUTOSCRIBE_DATABASE")
        .map(PathBuf::from)
        .unwrap_or(default_database_path()?);
    if let Some(parent) = database_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let db = Database::open_path(&database_path)?;
    db::migrate(&db)?;
    let server = serde_json::from_slice(&run_asc_capture(
        &asc_command(),
        ["control", "snapshot"],
        &[],
    )?)?;
    Ok(DefinePlanSnapshotOutput {
        ok: true,
        operation: "define-plan.snapshot",
        server,
        authored_plans: plan_repository::list(&db, "plans")?,
        authored_instructions: plan_repository::list(&db, "instructions")?,
    })
}

fn plan_save() -> ExitCode {
    command_output("plan.save", save_plan_from_stdin())
}

fn save_plan_from_stdin() -> Result<PlanSaveOutput, Box<dyn std::error::Error>> {
    let mut raw = String::new();
    io::stdin().read_to_string(&mut raw)?;
    let input: PlanSaveInput = serde_json::from_str(&raw)?;
    if input.version != 1 {
        return Err(format!("unsupported plan save version: {}", input.version).into());
    }
    if let Some(parent) = input.database_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let db = Database::open_path(&input.database_path)?;
    db::migrate(&db)?;
    plan_repository::save(&db, &input.plan, &input.instructions)?;
    let asc = asc_command();
    if !input.instructions.is_empty() {
        run_asc(
            &asc,
            ["upload", "instructions"],
            &ndjson(&input.instructions)?,
        )?;
    }
    let identity = input
        .plan
        .get("record_identity")
        .and_then(serde_json::Value::as_str)
        .ok_or("saved plan is missing record_identity")?
        .to_string();
    let plan_upload = serde_json::json!({"type":"plan","identity":identity.clone(),"content":input.plan["payload"],"extra":{}});
    run_asc(&asc, ["upload", "plans"], &ndjson(&[plan_upload])?)?;
    Ok(PlanSaveOutput {
        ok: true,
        operation: "plan.save",
        plan: identity,
        instructions: input.instructions.len(),
    })
}

fn command_output<T: Serialize>(
    operation: &'static str,
    result: Result<T, Box<dyn std::error::Error>>,
) -> ExitCode {
    match result {
        Ok(output) => {
            println!(
                "{}",
                serde_json::to_string(&output).expect("serializable output")
            );
            ExitCode::SUCCESS
        }
        Err(error) => {
            println!(
                "{}",
                serde_json::to_string(&ErrorOutput {
                    ok: false,
                    operation,
                    error: error.to_string()
                })
                .expect("serializable error")
            );
            ExitCode::FAILURE
        }
    }
}

fn run_asc_capture<I, S>(asc: &Path, args: I, input: &[u8]) -> Result<Vec<u8>, AscFailure>
where
    I: IntoIterator<Item = S>,
    S: AsRef<std::ffi::OsStr>,
{
    let mut child = Command::new(asc)
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| AscFailure {
            started: false,
            message: format!("could not start {}: {error}", asc.display()),
        })?;
    if let Some(mut stdin) = child.stdin.take() {
        use std::io::Write;
        stdin.write_all(input).map_err(|error| AscFailure {
            started: true,
            message: format!("could not stream payload to {}: {error}", asc.display()),
        })?;
    }
    let output = child.wait_with_output().map_err(|error| AscFailure {
        started: true,
        message: error.to_string(),
    })?;
    if output.status.success() {
        Ok(output.stdout)
    } else {
        let detail = String::from_utf8_lossy(if output.stderr.is_empty() {
            &output.stdout
        } else {
            &output.stderr
        });
        Err(AscFailure {
            started: true,
            message: format!(
                "{} exited with {}: {}",
                asc.display(),
                output.status,
                detail.trim()
            ),
        })
    }
}

fn dispatch_transmit() -> ExitCode {
    match transmit_from_args() {
        Ok(output) => {
            println!(
                "{}",
                serde_json::to_string(&output).expect("serializable transmit output")
            );
            ExitCode::SUCCESS
        }
        Err(error) => {
            println!(
                "{}",
                serde_json::to_string(&ErrorOutput {
                    ok: false,
                    operation: "dispatch.transmit",
                    error: error.to_string(),
                })
                .expect("serializable error output")
            );
            ExitCode::FAILURE
        }
    }
}

fn transmit_from_args() -> Result<DispatchTransmitOutput, Box<dyn std::error::Error>> {
    let identity = env::args()
        .nth(2)
        .filter(|value| !value.trim().is_empty())
        .ok_or("dispatch-transmit requires a dispatch identity")?;
    let database_path = env::var_os("AUTOSCRIBE_DATABASE")
        .map(PathBuf::from)
        .unwrap_or(default_database_path()?);
    let db = Database::open_path(&database_path)?;
    db::migrate(&db)?;
    let dispatch = DispatchId(identity);
    let saved = sync::pending_payload(&db, &dispatch)?;
    let actual_hash = dispatch::sha256_hex(&saved.bytes);
    if actual_hash != saved.sha256 {
        return Err(format!(
            "saved payload hash mismatch for {}: expected {}, computed {actual_hash}",
            dispatch.0, saved.sha256
        )
        .into());
    }
    let envelope: DispatchEnvelope = serde_json::from_slice(&saved.bytes)?;
    if envelope.version != 1 || envelope.calls.is_empty() || envelope.enqueue.is_empty() {
        return Err("saved dispatch envelope requires version 1 calls and enqueue records".into());
    }

    let sink = NoticeSink::new(&db);
    events::publish(
        &sink,
        autoscribe_service::types::Notice {
            kind: autoscribe_service::types::NoticeKind::Accepted,
            operation: "dispatch.transmit".into(),
            message: format!("Transmitting dispatch {}", dispatch.0),
        },
    )?;
    let asc = asc_command();
    if let Err(error) = run_asc(&asc, ["upload", "calls"], &ndjson(&envelope.calls)?) {
        let reason = error.to_string();
        sync::record_upload_outcome(
            &db,
            &dispatch,
            if error.started {
                UploadOutcome::Uncertain(reason.clone())
            } else {
                UploadOutcome::NotSent(reason.clone())
            },
        )?;
        publish_transmit_failure(&sink, &dispatch, &reason)?;
        return Err(reason.into());
    }
    if let Err(error) = run_asc(&asc, ["enqueue"], &ndjson(&envelope.enqueue)?) {
        let reason = error.to_string();
        sync::record_upload_outcome(&db, &dispatch, UploadOutcome::Uncertain(reason.clone()))?;
        publish_transmit_failure(&sink, &dispatch, &reason)?;
        return Err(reason.into());
    }
    sync::record_upload_outcome(&db, &dispatch, UploadOutcome::Acknowledged)?;
    events::publish(
        &sink,
        autoscribe_service::types::Notice {
            kind: autoscribe_service::types::NoticeKind::Completed,
            operation: "dispatch.transmit".into(),
            message: format!("Transmitted dispatch {}", dispatch.0),
        },
    )?;
    Ok(DispatchTransmitOutput {
        ok: true,
        operation: "dispatch.transmit",
        dispatch: dispatch.0,
        state: "acknowledged",
        calls: envelope.calls.len(),
        enqueue: envelope.enqueue.len(),
    })
}

fn default_database_path() -> Result<PathBuf, Box<dyn std::error::Error>> {
    let home = env::var_os("HOME").ok_or("HOME is not set")?;
    Ok(PathBuf::from(home).join(".local/share/autoscribe/service.sqlite"))
}

fn asc_command() -> PathBuf {
    env::var_os("ASC_BIN")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/home/jeremy/Python3.13Env/bin/asc"))
}

fn ndjson(records: &[serde_json::Value]) -> Result<Vec<u8>, serde_json::Error> {
    let mut output = Vec::new();
    for record in records {
        serde_json::to_writer(&mut output, record)?;
        output.push(b'\n');
    }
    Ok(output)
}

#[derive(Debug)]
struct AscFailure {
    started: bool,
    message: String,
}

impl std::fmt::Display for AscFailure {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl std::error::Error for AscFailure {}

fn run_asc<I, S>(asc: &Path, args: I, input: &[u8]) -> Result<(), AscFailure>
where
    I: IntoIterator<Item = S>,
    S: AsRef<std::ffi::OsStr>,
{
    let mut child = Command::new(asc)
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| AscFailure {
            started: false,
            message: format!("could not start {}: {error}", asc.display()),
        })?;
    if let Some(mut stdin) = child.stdin.take() {
        use std::io::Write;
        stdin.write_all(input).map_err(|error| AscFailure {
            started: true,
            message: format!("could not stream payload to {}: {error}", asc.display()),
        })?;
    }
    let output = child.wait_with_output().map_err(|error| AscFailure {
        started: true,
        message: format!("could not wait for {}: {error}", asc.display()),
    })?;
    if output.status.success() {
        return Ok(());
    }
    let detail = String::from_utf8_lossy(if output.stderr.is_empty() {
        &output.stdout
    } else {
        &output.stderr
    });
    Err(AscFailure {
        started: true,
        message: format!(
            "{} exited with {}: {}",
            asc.display(),
            output.status,
            detail.trim()
        ),
    })
}

fn publish_transmit_failure(
    sink: &NoticeSink<'_>,
    dispatch: &DispatchId,
    reason: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    events::publish(
        sink,
        autoscribe_service::types::Notice {
            kind: autoscribe_service::types::NoticeKind::NeedsDecision,
            operation: "dispatch.transmit".into(),
            message: format!("Dispatch {} needs review: {reason}", dispatch.0),
        },
    )?;
    Ok(())
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
