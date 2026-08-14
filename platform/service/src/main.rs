use autoscribe_service::{
    Service,
    db::{self, Database},
    dispatch, git,
    events::{self, NoticeSink},
    pandoc, plan_repository, response_repository,
    sync::{self, UploadOutcome},
    types::{CommitPurpose, CommitRequest, DispatchId, DispatchSource, LedgerSnapshotRequest,
        LedgerSource, PandocJob, PlanId, PrepareSavedDispatchRequest},
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
    inflight_ref: String,
    inflight_commit: String,
    payload_sha256: String,
    source_blobs: Vec<SourceBlobOutput>,
}

#[derive(Serialize)]
struct SourceBlobOutput { path: PathBuf, blob: String }

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
struct DispatchRunInput {
    version: u32,
    database_path: PathBuf,
    repository_path: PathBuf,
    pandoc_binary: PathBuf,
    pandoc_filter: PathBuf,
    pandoc_parallelism: usize,
    plan: String,
    paths: Vec<PathBuf>,
}

#[derive(Serialize)]
struct DispatchRunOutput {
    ok: bool,
    operation: &'static str,
    plan: String,
    records: usize,
    calls: Vec<String>,
    dispatch: String,
    inflight_commit: String,
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

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct GitFilesInput {
    version: u32,
    repository_path: PathBuf,
    action: String,
    #[serde(default)] paths: Vec<PathBuf>,
    path: Option<PathBuf>,
    message: Option<String>,
    purpose: Option<String>,
    revision: Option<String>,
    id: Option<String>,
    #[serde(default)] items: Vec<serde_json::Value>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ResponsesSnapshotInput { version:u32, database_path:PathBuf, repository_path:PathBuf }
#[derive(Serialize)]
struct ResponsesSnapshotOutput { ok:bool, operation:&'static str, responses:Vec<serde_json::Value> }
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ResponseDecideInput { version:u32, database_path:PathBuf, repository_path:PathBuf,
    result_identity:String, source_identity:String, source_path:Option<PathBuf>, outcome:String,
    replacement_text:Option<String> }
#[derive(Serialize)]
struct ResponseDecideOutput { ok:bool, operation:&'static str, result_identity:String,
    outcome:String, commit:Option<String> }
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct DispatchFinalizeInput { version:u32, database_path:PathBuf, repository_path:PathBuf,
    dispatch_identity:String, outcome:String, reason:Option<String> }

fn main() -> ExitCode {
    match env::args().nth(1).as_deref() {
        Some("dispatch-prepare") => return dispatch_prepare(),
        Some("dispatch-run") => return dispatch_run(),
        Some("dispatch-transmit") => return dispatch_transmit(),
        Some("define-plan-snapshot") => return define_plan_snapshot(),
        Some("plan-save") => return plan_save(),
        Some("git-files") => return command_output("git.files", git_files_from_stdin()),
        Some("responses-snapshot") => return command_output("responses.snapshot", responses_snapshot_from_stdin()),
        Some("response-decide") => return command_output("response.decide", response_decide_from_stdin()),
        Some("dispatch-finalize") => return command_output("dispatch.finalize", dispatch_finalize_from_stdin()),
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

fn git_files_from_stdin() -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let mut raw = String::new();
    io::stdin().read_to_string(&mut raw)?;
    let input: GitFilesInput = serde_json::from_str(&raw)?;
    if input.version != 1 { return Err("unsupported Git files version".into()); }
    let repo = input.repository_path.canonicalize()?;
    let output = match input.action.as_str() {
        "inspect" => {
            let items = if input.items.is_empty() {
                input.paths.iter().map(|path| serde_json::json!({"path":path})).collect()
            } else { input.items }
            ;
            let mut rows = Vec::new();
            for mut item in items {
                let Some(object) = item.as_object_mut() else { return Err("Git inspect items must be objects".into()); };
                let path = object.get("path").and_then(serde_json::Value::as_str).unwrap_or("").trim();
                if path.is_empty() {
                    object.insert("committable".into(), false.into());
                    object.insert("repo_state".into(), "unknown".into());
                    object.insert("error".into(), "selection row has no filepath".into());
                } else {
                    let status = git::status_code(&repo, Path::new(path))?;
                    let latest = git::last_commit(&repo, Path::new(path))?;
                    let state = if status.starts_with("??") { "untracked" } else if status.is_empty() {
                        if latest.is_some() { "clean" } else { "untracked" }
                    } else if status.contains('U') { "conflicted" } else { "modified" };
                    object.insert("repo_state".into(), state.into());
                    object.insert("git_status".into(), status.into());
                    object.insert("committable".into(), (state != "clean" && state != "conflicted").into());
                    object.insert("error".into(), if state == "clean" { "file has no uncommitted changes".into() } else if state == "conflicted" { "file has unresolved merge conflicts".into() } else { "".into() });
                    if let Some((hash, subject, timestamp)) = latest {
                        object.insert("latest_commit".into(), serde_json::json!({"hash":hash,"subject":subject,"timestamp":timestamp}));
                    }
                }
                rows.push(item);
            }
            let committable = rows.iter().filter(|row| row["committable"] == true).count();
            serde_json::json!({"ok":true,"operation":"git.files","items":rows,
                "summary":{"count":rows.len(),"committable":committable,"blocked":rows.len()-committable}})
        }
        "commit" => {
            let purpose = match input.purpose.as_deref() { Some("lock") => CommitPurpose::Lock, _ => CommitPurpose::Version };
            let commit = git::commit(&repo, CommitRequest { paths: input.paths.clone(), message: input.message.ok_or("commit message required")?, purpose })?;
            serde_json::json!({"ok":true,"operation":"git.files","commit":{"hash":commit.0},"count":input.paths.len(),"files":input.paths})
        }
        "history" => {
            let path = input.path.ok_or("history path required")?;
            let head = git::head(&repo)?.0;
            let latest = git::last_commit(&repo, &path)?.map(|row| row.0).unwrap_or_default();
            let rows = git::file_history(&repo, &path)?.into_iter().map(|(hash,date,author,subject)| serde_json::json!({
                "hash":hash,"date":date,"author":author,"subject":subject,"refs":[],"transport_refs":[],
                "kind":if subject.starts_with("AutoScribe") {"AutoScribe"} else {"Commit"},"change":"Recorded","added":0,"deleted":0,
                "is_head":hash==head,"is_current_file_version":hash==latest
            })).collect::<Vec<_>>();
            serde_json::json!({"ok":true,"operation":"git.files","items":rows})
        }
        "stash-list" => serde_json::json!({"ok":true,"operation":"git.files","items":git::list_file_stashes(&repo, input.path.as_deref())?}),
        "stash-create" => serde_json::json!({"ok":true,"operation":"git.files","item":git::stash_file(&repo, &input.path.ok_or("stash path required")?)?}),
        "stash-restore" => serde_json::json!({"ok":true,"operation":"git.files","item":git::restore_file_stash(&repo, &input.path.ok_or("stash path required")?, &input.id.ok_or("stash id required")?)?}),
        "stash-drop" => serde_json::json!({"ok":true,"operation":"git.files","item":git::drop_file_stash(&repo, &input.path.ok_or("stash path required")?, &input.id.ok_or("stash id required")?)?}),
        "restore-version" => {
            let (source, safety_tag) = git::restore_file_to_index(&repo, &input.path.ok_or("restore path required")?, &input.revision.ok_or("revision required")?)?;
            serde_json::json!({"ok":true,"operation":"git.files","source":source,"safety_tag":safety_tag})
        }
        _ => return Err(format!("unknown Git files action: {}", input.action).into()),
    };
    Ok(output)
}

fn responses_snapshot_from_stdin()->Result<ResponsesSnapshotOutput,Box<dyn std::error::Error>>{
    let input:ResponsesSnapshotInput=read_json_stdin()?;
    if input.version!=1{return Err("unsupported responses snapshot version".into());}
    let _=input.repository_path.canonicalize()?;let db=open_database(&input.database_path)?;
    let records=normalize_response_records(&run_asc_capture(&asc_command(),["export","extract-pending"],&[])?)?;
    response_repository::store_pending(&db,&records)?;
    Ok(ResponsesSnapshotOutput{ok:true,operation:"responses.snapshot",responses:response_repository::pending(&db)?})
}
fn dispatch_finalize_from_stdin()->Result<serde_json::Value,Box<dyn std::error::Error>>{
    let input:DispatchFinalizeInput=read_json_stdin()?;
    if input.version!=1{return Err("unsupported dispatch finalize version".into());}
    let db=open_database(&input.database_path)?;let repository=input.repository_path.canonicalize()?;
    db::ensure_terminal_ready(&db,&input.dispatch_identity)?;
    let event=git::append_dispatch_terminal_event(&repository,&input.dispatch_identity,&input.outcome,input.reason.as_deref())?;
    db::clear_terminal_dispatch(&db,&input.dispatch_identity)?;
    Ok(serde_json::json!({"ok":true,"operation":"dispatch.finalize","dispatch":input.dispatch_identity,"outcome":input.outcome,"forensic_commit":event.0}))
}
fn response_decide_from_stdin()->Result<ResponseDecideOutput,Box<dyn std::error::Error>>{
    let input:ResponseDecideInput=read_json_stdin()?;
    if input.version!=1||!matches!(input.outcome.as_str(),"accepted"|"declined"){return Err("response decision requires version 1 and accepted or declined outcome".into());}
    let db=open_database(&input.database_path)?;
    let (state,dispatch,_,source_blob,stored_outcome,_stored_path,stored_commit,stored_forensic)=response_repository::require_pending(&db,&input.result_identity,&input.source_identity)?;
    let repository=input.repository_path.canonicalize()?;
    if state=="written"{
        if stored_outcome.as_deref()!=Some(input.outcome.as_str()){return Err("response already written with another outcome".into());}
        if stored_forensic.is_none(){let event=git::append_response_event(&repository,&dispatch,&input.result_identity,&input.source_identity,&input.outcome,stored_commit.as_deref())?;response_repository::mark_forensic(&db,&input.result_identity,&event.0)?;}
        run_asc(&asc_command(),["export","update-exports",input.result_identity.as_str()],&[])?;
        response_repository::complete(&db,&input.result_identity)?;
        return Ok(ResponseDecideOutput{ok:true,operation:"response.decide",result_identity:input.result_identity,outcome:input.outcome,commit:stored_commit});
    }
    let mut commit=None;
    let source_path=if input.outcome=="accepted"{let relative=input.source_path.as_ref().ok_or("accepted response requires source_path")?;let replacement=input.replacement_text.as_ref().ok_or("accepted response requires replacement_text")?;
        let statuses=git::inspect(&repository,&[relative.clone()])?;if statuses.first().is_none_or(|status|!status.tracked||status.dirty){return Err(format!("response target must be tracked and clean: {}",relative.display()).into());}
        if git::worktree_blob(&repository,relative)?!=source_blob{return Err(format!("source changed since dispatch: {}",relative.display()).into());}
        let target=repository.join(relative);let original=std::fs::read_to_string(&target)?;require_markdown_slug(&original,&input.source_identity)?;require_markdown_slug(replacement,&input.source_identity)?;std::fs::write(&target,replacement)?;
        match git::commit(&repository,CommitRequest{paths:vec![relative.clone()],message:format!("Accept AutoScribe response {}",input.source_identity),purpose:CommitPurpose::DispatchWriteback}){Ok(value)=>commit=Some(value.0),Err(error)=>{let _=std::fs::write(&target,original);return Err(error.into());}}
        Some(relative.to_string_lossy().replace('\\',"/"))}else{None};
    response_repository::mark_written(&db,&input.result_identity,&input.outcome,source_path.as_deref(),commit.as_deref())?;
    let event=git::append_response_event(&repository,&dispatch,&input.result_identity,&input.source_identity,&input.outcome,commit.as_deref())?;
    response_repository::mark_forensic(&db,&input.result_identity,&event.0)?;
    run_asc(&asc_command(),["export","update-exports",input.result_identity.as_str()],&[])?;
    response_repository::complete(&db,&input.result_identity)?;
    Ok(ResponseDecideOutput{ok:true,operation:"response.decide",result_identity:input.result_identity,outcome:input.outcome,commit})
}
fn read_json_stdin<T:for<'de>Deserialize<'de>>()->Result<T,Box<dyn std::error::Error>>{let mut raw=String::new();io::stdin().read_to_string(&mut raw)?;Ok(serde_json::from_str(&raw)?)}
fn open_database(path:&Path)->Result<Database,Box<dyn std::error::Error>>{if let Some(parent)=path.parent(){std::fs::create_dir_all(parent)?;}let db=Database::open_path(path)?;db::migrate(&db)?;Ok(db)}
fn normalize_response_records(bytes:&[u8])->Result<Vec<serde_json::Value>,Box<dyn std::error::Error>>{let text=std::str::from_utf8(bytes)?;let mut records=Vec::new();for(index,line)in text.lines().filter(|line|!line.trim().is_empty()).enumerate(){let raw:serde_json::Value=serde_json::from_str(line)?;let first=|keys:&[&str]|keys.iter().find_map(|key|raw.get(*key).and_then(serde_json::Value::as_str)).map(str::trim).filter(|v|!v.is_empty()).unwrap_or("").to_string();let source=first(&["record_identity","source_identity","prompt_slug","slug"]);let call=first(&["call_identity","call","identity"]);let result=first(&["result_identity","response_identity","identity","call_identity"]);let content=response_content(&raw).unwrap_or_default();if source.is_empty()||call.is_empty()||result.is_empty()||content.trim().is_empty(){return Err(format!("pending response {} lacks source, call, result, or content",index+1).into());}records.push(serde_json::json!({"source_identity":source,"call_identity":call,"result_identity":result,"content":content,"raw":raw}));}Ok(records)}
fn response_content(value:&serde_json::Value)->Option<String>{if let Some(object)=value.as_object(){for key in["record_content","result_content","content","body","text"]{if let Some(found)=object.get(key).and_then(response_content){if !found.trim().is_empty(){return Some(found);}}}}value.as_str().map(str::to_string)}
fn require_markdown_slug(text:&str,expected:&str)->Result<(),Box<dyn std::error::Error>>{let mut lines=text.lines();if lines.next().map(str::trim)!=Some("---"){return Err("Markdown target requires frontmatter".into());}for line in lines{let clean=line.trim();if clean=="---"{break;}if let Some(value)=clean.strip_prefix("slug:"){let actual=value.trim().trim_matches(['\'','"']);return if actual==expected{Ok(())}else{Err(format!("slug mismatch: expected {expected}, found {actual}").into())};}}Err(format!("slug mismatch: expected {expected}, found no slug").into())}

fn dispatch_run() -> ExitCode {
    match run_dispatch_from_stdin() {
        Ok(output) => {
            println!(
                "{}",
                serde_json::to_string(&output).expect("serializable dispatch run output")
            );
            ExitCode::SUCCESS
        }
        Err(error) => {
            println!(
                "{}",
                serde_json::to_string(&ErrorOutput {
                    ok: false,
                    operation: "dispatch.run",
                    error: error.to_string(),
                })
                .expect("serializable error output")
            );
            ExitCode::FAILURE
        }
    }
}

fn run_dispatch_from_stdin() -> Result<DispatchRunOutput, Box<dyn std::error::Error>> {
    let mut raw = String::new();
    io::stdin().read_to_string(&mut raw)?;
    let input: DispatchRunInput = serde_json::from_str(&raw)?;
    if input.version != 1 {
        return Err(format!("unsupported dispatch run version: {}", input.version).into());
    }
    if input.plan.trim().is_empty() {
        return Err("dispatch run requires a plan".into());
    }
    if input.paths.is_empty() {
        return Err("dispatch run requires at least one path".into());
    }
    if !input.pandoc_binary.is_absolute() || !input.pandoc_filter.is_absolute() {
        return Err("dispatch run requires absolute Pandoc executable and filter paths".into());
    }
    let repository = input.repository_path.canonicalize()?;
    if let Some(parent) = input.database_path.parent() { std::fs::create_dir_all(parent)?; }
    let database = Database::open_path(&input.database_path)?;
    db::migrate(&database)?;
    let mut paths = input.paths;
    paths.sort();
    paths.dedup();
    let mut jobs = Vec::new();
    let mut ledger_sources = Vec::new();
    for relative in paths {
        if relative.is_absolute()
            || relative
                .components()
                .any(|part| matches!(part, std::path::Component::ParentDir))
        {
            return Err(format!(
                "dispatch path must be repository-relative: {}",
                relative.display()
            )
            .into());
        }
        let source = repository.join(&relative).canonicalize()?;
        if !source.is_file() || !source.starts_with(&repository) {
            return Err(format!(
                "dispatch path is unavailable or outside repository: {}",
                relative.display()
            )
            .into());
        }
        ledger_sources.push((relative.clone(), std::fs::read(&source)?));
        jobs.push(PandocJob {
            identity: relative.to_string_lossy().replace('\\', "/"),
            working_directory: repository.clone(),
            arguments: vec![
                source.to_string_lossy().into_owned(),
                "--from=markdown+yaml_metadata_block+fenced_divs".into(),
                format!("--lua-filter={}", input.pandoc_filter.display()),
                "--to=native".into(),
                "--output=/dev/null".into(),
            ],
        });
    }
    let outcomes = pandoc::run_parallel(&input.pandoc_binary, jobs, input.pandoc_parallelism)?;
    let mut calls = Vec::new();
    let mut enqueue = Vec::new();
    let mut identities = Vec::new();
    for outcome in outcomes {
        if outcome.exit_code != Some(0) || outcome.error.is_some() {
            let detail = outcome
                .error
                .unwrap_or_else(|| String::from_utf8_lossy(&outcome.stderr).trim().into());
            return Err(format!("{}: Pandoc conversion failed: {detail}", outcome.identity).into());
        }
        let text = std::str::from_utf8(&outcome.stdout)?;
        let line = text
            .lines()
            .find(|line| line.trim_start().starts_with('{'))
            .ok_or_else(|| format!("{}: Pandoc emitted no NDJSON record", outcome.identity))?;
        let record: serde_json::Value = serde_json::from_str(line)?;
        let identity = record
            .get("record_identity")
            .and_then(serde_json::Value::as_str)
            .unwrap_or("")
            .trim()
            .to_string();
        if identity.is_empty() {
            return Err(format!(
                "{}: Pandoc record is missing record_identity",
                outcome.identity
            )
            .into());
        }
        let payload = record
            .get("payload")
            .and_then(serde_json::Value::as_object)
            .ok_or_else(|| format!("{identity}: Pandoc payload must be an object"))?;
        let content = payload
            .get("content")
            .and_then(serde_json::Value::as_str)
            .unwrap_or("");
        if content.trim().is_empty() {
            return Err(format!("{identity}: Pandoc content is blank").into());
        }
        let metadata = payload
            .iter()
            .filter(|(key, _)| key.as_str() != "content")
            .map(|(key, value)| (key.clone(), value.clone()))
            .collect::<serde_json::Map<_, _>>();
        calls.push(serde_json::json!({"type":"call","identity":identity,"content":content,
            "extra":{"filename_hint":Path::new(&outcome.identity).file_name().and_then(|name| name.to_str()).unwrap_or(&outcome.identity),
            "source_path":outcome.identity,"metadata":metadata}}));
        let mut manifest = serde_json::json!({"call":identity,"plan":input.plan});
        if let Some(directive) = record
            .get("directive")
            .and_then(serde_json::Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
        {
            manifest["directive"] = serde_json::Value::String(directive.into());
        }
        enqueue.push(manifest);
        identities.push(identity);
    }
    let asc = asc_command();
    let pending_output = run_asc_capture(&asc, ["export", "list-pending", "--ndjson"], &[])?;
    let pending = pending_source_identities(&pending_output)?;
    let blocked = identities
        .iter()
        .filter(|identity| pending.contains(identity.as_str()))
        .cloned()
        .collect::<Vec<_>>();
    if !blocked.is_empty() {
        return Err(format!(
            "dispatch blocked by pending unexported responses: {}",
            blocked.join(", ")
        )
        .into());
    }
    let dispatch = format!(
        "run-{}-{}",
        std::process::id(),
        std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)?.as_nanos()
    );
    let sources = identities.iter().zip(ledger_sources.into_iter())
        .map(|(slug, (path, bytes))| LedgerSource { slug: slug.clone(), path, bytes })
        .collect::<Vec<_>>();
    let ledger = git::append_inflight_snapshot(&repository, &LedgerSnapshotRequest {
        dispatch: DispatchId(dispatch.clone()),
        plan: PlanId(input.plan.clone()),
        sources: sources.clone(),
    })?;
    let source_rows = sources.iter().zip(ledger.blobs.iter()).map(|(source, (path, blob))| {
        (source.slug.clone(), path.to_string_lossy().into_owned(), blob.clone())
    }).collect::<Vec<_>>();
    db::record_inflight(
        &database, &dispatch, &input.plan, &ledger.reference, &ledger.commit.0, &source_rows,
    )?;
    run_asc(&asc, ["upload", "calls"], &ndjson(&calls)?)?;
    run_asc(&asc, ["enqueue"], &ndjson(&enqueue)?)?;
    Ok(DispatchRunOutput {
        ok: true,
        operation: "dispatch.run",
        plan: input.plan,
        records: identities.len(),
        calls: identities,
        dispatch,
        inflight_commit: ledger.commit.0,
    })
}

fn pending_source_identities(
    bytes: &[u8],
) -> Result<std::collections::BTreeSet<String>, Box<dyn std::error::Error>> {
    let text = std::str::from_utf8(bytes)?;
    let mut identities = std::collections::BTreeSet::new();
    for (index, line) in text.lines().enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let record: serde_json::Value = serde_json::from_str(line).map_err(|error| {
            format!(
                "invalid pending-response NDJSON on line {}: {error}",
                index + 1
            )
        })?;
        let identity = ["record_identity", "source_identity", "prompt_slug", "slug"]
            .into_iter()
            .find_map(|key| record.get(key).and_then(serde_json::Value::as_str))
            .unwrap_or("")
            .trim();
        if identity.is_empty() {
            return Err(format!(
                "pending-response record {} has no source identity",
                index + 1
            )
            .into());
        }
        identities.insert(identity.to_string());
    }
    Ok(identities)
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
        inflight_ref: prepared.ledger.reference,
        inflight_commit: prepared.ledger.commit.0,
        payload_sha256: prepared.payload_sha256,
        source_blobs: prepared.ledger.blobs.into_iter().map(|(path, blob)| SourceBlobOutput { path, blob }).collect(),
    })
}
