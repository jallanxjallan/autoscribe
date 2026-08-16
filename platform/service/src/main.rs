use autoscribe_service::{
    Service,
    db::{self, Database},
    git, instruction_sync,
    pandoc, plan_repository, reconcile, response_repository,
    types::{CommitPurpose, CommitRequest, DispatchId, LedgerSnapshotRequest,
        LedgerSource, PandocJob, PlanId},
};
use serde::{Deserialize, Serialize};
use std::{
    env,
    io::{self, Read},
    path::{Path, PathBuf},
    process::{Command, ExitCode, Stdio},
};

#[derive(Serialize)]
struct ErrorOutput {
    ok: bool,
    operation: &'static str,
    error: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct DispatchRunInput {
    version: u32,
    plan: String,
    documents: Vec<String>,
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

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct InstructionSyncInput {
    version: u32,
    root: PathBuf,
    paths: Vec<PathBuf>,
}

#[derive(Serialize)]
struct InstructionSyncOutput {
    ok: bool,
    operation: &'static str,
    scanned: usize,
    selected: usize,
    uploaded: usize,
    hashes_compared: usize,
    items: Vec<instruction_sync::SyncItem>,
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
struct VersionInput { version:u32 }
fn main() -> ExitCode {
    match env::args().nth(1).as_deref() {
        Some("dispatch-run") => return dispatch_run(),
        Some("define-plan-snapshot") => return define_plan_snapshot(),
        Some("system-snapshot") => return command_output("system.snapshot", system_snapshot_from_stdin()),
        Some("plan-save") => return plan_save(),
        Some("instructions-sync") => return command_output("instructions.sync", instructions_sync_from_stdin()),
        Some("git-files") => return command_output("git.files", git_files_from_stdin()),
        Some("write-responses") => return write_responses(),
        Some("upload-instructions") => return command_output("instructions.upload", upload_instructions()),
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

fn upload_instructions()->Result<serde_json::Value,Box<dyn std::error::Error>>{
    let arguments=env::args_os().skip(2).collect::<Vec<_>>();
    let dry_run=arguments.iter().any(|value|value=="--dry-run");
    let root=arguments.iter().find(|value|*value!="--dry-run").map(PathBuf::from)
        .unwrap_or(std::env::current_dir()?.join("instructions"));
    let root=root.canonicalize()?;
    let manifest:serde_json::Value=serde_json::from_slice(&run_asc_capture(&asc_command(),["control","instruction-manifest"],&[])?)?;
    let plan=instruction_sync::plan(instruction_sync::scan(&root)?,&manifest)?;
    let uploaded=plan.upload.len();let current=plan.items.len()-uploaded;
    if !dry_run&&!plan.upload.is_empty(){let records=plan.upload.iter().map(instruction_sync::upload_record).collect::<Vec<_>>();run_asc(&asc_command(),["upload","instructions"],&ndjson(&records)?)?;}
    Ok(serde_json::json!({"ok":true,"operation":"instructions.upload","root":root,"dry_run":dry_run,
        "scanned":plan.items.len(),"current":current,"uploaded":if dry_run{0}else{uploaded},"would_upload":uploaded,
        "hashes_compared":plan.hashes_compared,"items":plan.items}))
}

fn system_snapshot_from_stdin() -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let input: VersionInput = read_json_stdin()?;
    if input.version != 1 { return Err("unsupported system snapshot version".into()); }
    let repository = git::root(&std::env::current_dir()?)?;
    let db = open_database(&configured_database_path()?)?;
    Ok(serde_json::json!({
        "ok":true,
        "operation":"system.snapshot",
        "git":git::summary(&repository)?,
        "pipeline":db::system_counts(&db)?
    }))
}

fn instructions_sync_from_stdin() -> Result<InstructionSyncOutput, Box<dyn std::error::Error>> {
    let input: InstructionSyncInput = read_json_stdin()?;
    if input.version != 1 { return Err("unsupported instruction sync version".into()); }
    let root = input.root.canonicalize()?;
    let selected = input.paths.into_iter()
        .map(|path| path.to_string_lossy().replace('\\', "/"))
        .collect::<std::collections::BTreeSet<_>>();
    if selected.is_empty() { return Err("instruction sync requires selected paths".into()); }
    let all = instruction_sync::scan(&root)?;
    let scanned = all.len();
    let local = all.into_iter()
        .filter(|item| selected.contains(&item.relative_path))
        .collect::<Vec<_>>();
    if local.len() != selected.len() {
        let resolved = local.iter().map(|item| item.relative_path.clone()).collect::<std::collections::BTreeSet<_>>();
        let missing = selected.difference(&resolved).cloned().collect::<Vec<_>>();
        return Err(format!("selected instruction paths were not found: {}", missing.join(", ")).into());
    }
    let manifest: serde_json::Value = serde_json::from_slice(&run_asc_capture(
        &asc_command(), ["control", "instruction-manifest"], &[],
    )?)?;
    let plan = instruction_sync::plan(local, &manifest)?;
    let uploaded = plan.upload.len();
    if !plan.upload.is_empty() {
        let records = plan.upload.iter().map(instruction_sync::upload_record).collect::<Vec<_>>();
        run_asc(&asc_command(), ["upload", "instructions"], &ndjson(&records)?)?;
    }
    Ok(InstructionSyncOutput {
        ok: true,
        operation: "instructions.sync",
        scanned,
        selected: selected.len(),
        uploaded,
        hashes_compared: plan.hashes_compared,
        items: plan.items,
    })
}

fn git_files_from_stdin() -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let mut raw = String::new();
    io::stdin().read_to_string(&mut raw)?;
    let input: GitFilesInput = serde_json::from_str(&raw)?;
    if input.version != 1 { return Err("unsupported Git files version".into()); }
    let repo = std::env::current_dir()?.canonicalize()?;
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

fn write_responses() -> ExitCode {
    match write_responses_from_stdin() {
        Ok(records) => {
            for record in records {
                println!("{}", serde_json::to_string(&record).expect("serializable writeback result"));
            }
            ExitCode::SUCCESS
        }
        Err(error) => {
            println!("{}", serde_json::to_string(&ErrorOutput {
                ok: false,
                operation: "write.responses",
                error: error.to_string(),
            }).expect("serializable writeback error"));
            ExitCode::FAILURE
        }
    }
}

fn write_responses_from_stdin() -> Result<Vec<serde_json::Value>, Box<dyn std::error::Error>> {
    let input: VersionInput = read_json_stdin()?;
    if input.version != 1 { return Err("unsupported Write Responses version".into()); }
    let repository = git::root(&std::env::current_dir()?)?;
    let db = open_database(&configured_database_path()?)?;
    let records = normalize_response_records(&run_asc_capture(
        &asc_command(), ["export", "extract-pending"], &[],
    )?)?;
    response_repository::store_pending(&db, &records)?;
    let pending = response_repository::pending(&db)?;
    let mut manifest = Vec::new();
    for record in pending {
        let result_identity = record.get("result_identity").and_then(serde_json::Value::as_str)
            .unwrap_or("unknown-result").to_string();
        let source_identity = record.get("source_identity").and_then(serde_json::Value::as_str)
            .unwrap_or("unknown-source").to_string();
        match commit_writeback(&repository, &db, record) {
            Ok(item) => manifest.push(item),
            Err(error) => manifest.push(serde_json::json!({
                "type":"writeback-result",
                "status":"failed",
                "result_identity":result_identity,
                "source_identity":source_identity,
                "error":error.to_string()
            })),
        }
    }
    Ok(manifest)
}

fn commit_writeback(
    repository: &Path,
    db: &Database,
    record: serde_json::Value,
) -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let result = record.get("result_identity").and_then(serde_json::Value::as_str)
        .ok_or("pending response is missing result_identity")?.to_string();
    let source = record.get("source_identity").and_then(serde_json::Value::as_str)
        .ok_or("pending response is missing source_identity")?.to_string();
    let path = record.get("source_path").and_then(serde_json::Value::as_str)
        .ok_or("pending response is missing source_path")?.to_string();
    let (state, dispatch_identity, _, _, stored_outcome, _, stored_commit, stored_forensic) =
        response_repository::require_pending(db, &result, &source)?;

    let (commit, checkpoint_commit) = if state == "written" {
        if stored_outcome.as_deref() != Some("accepted") {
            return Err("response was already written with another outcome".into());
        }
        (stored_commit.ok_or("written response has no writeback commit")?, None)
    } else {
        let relative = PathBuf::from(&path);
        if relative.is_absolute() || relative.components().any(|part| !matches!(part, std::path::Component::Normal(_))) {
            return Err(format!("writeback path is not repository-relative: {path}").into());
        }
        let target = repository.join(&relative);
        let target_metadata = std::fs::symlink_metadata(&target)?;
        if target_metadata.file_type().is_symlink() || !target_metadata.is_file() {
            return Err(format!("writeback target must be a regular repository file: {path}").into());
        }
        if !target.canonicalize()?.starts_with(repository) {
            return Err(format!("writeback target resolves outside the repository: {path}").into());
        }
        let current = std::fs::read_to_string(&target)?;
        if markdown_slug(&current).as_deref() != Some(source.as_str()) {
            return Err(format!("current target slug does not match {source}: {path}").into());
        }
        let response = record.get("content").and_then(serde_json::Value::as_str)
            .ok_or("pending response is missing content")?;
        let replacement = set_document_review_metadata(&preserve_frontmatter(&current, response)?)?;
        let status = git::inspect(repository, std::slice::from_ref(&relative))?
            .into_iter().next().ok_or("writeback target has no Git status")?;
        let last = git::last_commit(repository, &relative)?;
        let writeback_subject = format!("Accept AutoScribe response {source}");
        if !status.dirty && current == replacement &&
            last.as_ref().is_some_and(|(_, subject, _)| subject == &writeback_subject)
        {
            let committed = last.expect("checked above").0;
            response_repository::mark_written(db, &result, "accepted", Some(&path), Some(&committed))?;
            (committed, None)
        } else {
        let checkpoint = if status.dirty {
            Some(git::commit(repository, CommitRequest {
                paths: vec![relative.clone()],
                message: format!("Checkpoint before AutoScribe writeback {source}"),
                purpose: CommitPurpose::WritebackCheckpoint,
            })?.0)
        } else {
            last.as_ref().filter(|(_, subject, _)| {
                subject == &format!("Checkpoint before AutoScribe writeback {source}")
            }).map(|(hash, _, _)| hash.clone())
        };
        std::fs::write(&target, &replacement)?;
        let committed = match git::commit(repository, CommitRequest {
            paths: vec![relative],
            message: writeback_subject,
            purpose: CommitPurpose::DispatchWriteback,
        }) {
            Ok(value) => value.0,
            Err(error) => {
                let _ = std::fs::write(&target, current);
                return Err(error.into());
            }
        };
        response_repository::mark_written(db, &result, "accepted", Some(&path), Some(&committed))?;
        (committed, checkpoint)
        }
    };

    if stored_forensic.is_none() {
        let event = git::append_response_event(
            repository, &dispatch_identity, &result, &source, "accepted", Some(&commit),
        )?;
        response_repository::mark_forensic(db, &result, &event.0)?;
    }
    run_asc(&asc_command(), ["export", "update-exports", result.as_str()], &[])?;
    response_repository::complete(db, &result)?;
    Ok(serde_json::json!({
        "type":"writeback-result",
        "status":"committed",
        "result_identity":result,
        "source_identity":source,
        "path":path,
        "commit":commit,
        "checkpoint_commit":checkpoint_commit,
        "document_status":"needs-review",
        "producer":"ai"
    }))
}

fn read_json_stdin<T:for<'de>Deserialize<'de>>()->Result<T,Box<dyn std::error::Error>>{let mut raw=String::new();io::stdin().read_to_string(&mut raw)?;Ok(serde_json::from_str(&raw)?)}
fn open_database(path:&Path)->Result<Database,Box<dyn std::error::Error>>{if let Some(parent)=path.parent(){std::fs::create_dir_all(parent)?;}let db=Database::open_path(path)?;db::migrate(&db)?;Ok(db)}
fn normalize_response_records(bytes:&[u8])->Result<Vec<serde_json::Value>,Box<dyn std::error::Error>>{let text=std::str::from_utf8(bytes)?;let mut records=Vec::new();for(index,line)in text.lines().filter(|line|!line.trim().is_empty()).enumerate(){let raw:serde_json::Value=serde_json::from_str(line)?;let first=|keys:&[&str]|keys.iter().find_map(|key|raw.get(*key).and_then(serde_json::Value::as_str)).map(str::trim).filter(|v|!v.is_empty()).unwrap_or("").to_string();let source=first(&["record_identity","source_identity","prompt_slug","slug"]);let call=first(&["call_identity","call","identity"]);let result=first(&["result_identity","response_identity","identity","call_identity"]);let content=response_content(&raw).unwrap_or_default();if source.is_empty()||call.is_empty()||result.is_empty()||content.trim().is_empty(){return Err(format!("pending response {} lacks source, call, result, or content",index+1).into());}records.push(serde_json::json!({"source_identity":source,"call_identity":call,"result_identity":result,"content":content,"raw":raw}));}Ok(records)}
fn response_content(value:&serde_json::Value)->Option<String>{if let Some(object)=value.as_object(){for key in["record_content","result_content","content","body","text"]{if let Some(found)=object.get(key).and_then(response_content){if !found.trim().is_empty(){return Some(found);}}}}value.as_str().map(str::to_string)}

fn configured_database_path() -> Result<PathBuf, Box<dyn std::error::Error>> {
    if let Some(path) = env::var_os("AUTOSCRIBE_DATABASE") {
        return Ok(PathBuf::from(path));
    }
    default_database_path()
}

fn markdown_slug(text: &str) -> Option<String> {
    let mut lines = text.lines();
    if lines.next().map(str::trim) != Some("---") { return None; }
    for line in lines {
        if line.trim() == "---" { break; }
        if line.chars().next().is_some_and(char::is_whitespace) { continue; }
        if let Some(value) = line.strip_prefix("slug:") {
            let slug = value.trim().trim_matches(['\'', '"']);
            return (!slug.is_empty()).then(|| slug.to_string());
        }
    }
    None
}

fn markdown_body(text: &str) -> &str {
    if !text.starts_with("---") { return text; }
    let bytes = text.as_bytes();
    let mut line_start = text.find('\n').map(|index| index + 1).unwrap_or(text.len());
    while line_start < text.len() {
        let line_end = text[line_start..].find('\n').map(|index| line_start + index).unwrap_or(text.len());
        if text[line_start..line_end].trim_end_matches('\r').trim() == "---" {
            return &text[if line_end < bytes.len() { line_end + 1 } else { line_end }..];
        }
        line_start = if line_end < bytes.len() { line_end + 1 } else { line_end };
    }
    text
}

fn preserve_frontmatter(old: &str, response: &str) -> Result<String, Box<dyn std::error::Error>> {
    let old_body = markdown_body(old);
    if old_body.len() == old.len() { return Err("writeback source has no complete frontmatter".into()); }
    let prefix_len = old.len() - old_body.len();
    Ok(format!("{}{}", &old[..prefix_len], markdown_body(response)))
}

fn set_document_review_metadata(text: &str) -> Result<String, Box<dyn std::error::Error>> {
    let body = markdown_body(text);
    if body.len() == text.len() { return Err("writeback target has no complete frontmatter".into()); }
    let prefix_len = text.len() - body.len();
    let prefix = &text[..prefix_len];
    let newline = if prefix.contains("\r\n") { "\r\n" } else { "\n" };
    let normalized = prefix.replace("\r\n", "\n");
    let mut lines = normalized.lines().map(str::to_string).collect::<Vec<_>>();
    if lines.first().map(String::as_str) != Some("---") {
        return Err("writeback target has invalid frontmatter opening".into());
    }
    let closing = lines.iter().rposition(|line| line.trim() == "---")
        .ok_or("writeback target has invalid frontmatter closing")?;
    let mut status_found = false;
    let mut producer_found = false;
    for line in lines.iter_mut().take(closing).skip(1) {
        if line.starts_with("status:") {
            *line = "status: needs-review".into();
            status_found = true;
        } else if line.starts_with("producer:") {
            *line = "producer: ai".into();
            producer_found = true;
        }
    }
    let insertion = lines.iter().take(closing).position(|line| line.starts_with("slug:"))
        .map(|index| index + 1).unwrap_or(closing);
    if !status_found {
        lines.insert(insertion, "status: needs-review".into());
    }
    let adjusted_closing = if status_found { closing } else { closing + 1 };
    if !producer_found {
        lines.insert(adjusted_closing, "producer: ai".into());
    }
    let mut rebuilt = lines.join(newline);
    rebuilt.push_str(newline);
    rebuilt.push_str(body);
    Ok(rebuilt)
}

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
    let input: DispatchRunInput = read_json_stdin()?;
    if input.version != 1 {
        return Err(format!("unsupported dispatch run version: {}", input.version).into());
    }
    if input.plan.trim().is_empty() {
        return Err("dispatch run requires a plan".into());
    }
    if input.documents.is_empty() {
        return Err("dispatch run requires at least one document slug".into());
    }
    let repository = git::root(&std::env::current_dir()?)?;
    let database_path = configured_database_path()?;
    if let Some(parent) = database_path.parent() { std::fs::create_dir_all(parent)?; }
    let database = Database::open_path(&database_path)?;
    db::migrate(&database)?;
    let server = reconcile_authored_catalog(&database, &asc_command())?;
    require_plan_slug(&server, &input.plan)?;
    let documents = resolve_document_slugs(&repository, &input.documents)?;
    let pandoc_binary = configured_pandoc_binary()?;
    let pandoc_filter = configured_pandoc_filter()?;
    let pandoc_parallelism = configured_pandoc_parallelism();
    let mut jobs = Vec::new();
    let mut ledger_sources = Vec::new();
    for (slug, relative) in &documents {
        let source = repository.join(&relative).canonicalize()?;
        if !source.is_file() || !source.starts_with(&repository) {
            return Err(format!(
                "dispatch path is unavailable or outside repository: {}",
                relative.display()
            )
            .into());
        }
        ledger_sources.push(LedgerSource {
            slug: slug.clone(),
            path: relative.clone(),
            bytes: std::fs::read(&source)?,
        });
        jobs.push(PandocJob {
            identity: relative.to_string_lossy().replace('\\', "/"),
            working_directory: repository.clone(),
            arguments: vec![
                source.to_string_lossy().into_owned(),
                "--from=markdown+yaml_metadata_block+fenced_divs".into(),
                format!("--lua-filter={}", pandoc_filter.display()),
                "--to=native".into(),
                "--output=/dev/null".into(),
            ],
        });
    }
    let outcomes = pandoc::run_parallel(&pandoc_binary, jobs, pandoc_parallelism)?;
    let mut calls = Vec::new();
    let mut enqueue = Vec::new();
    let mut identities = Vec::new();
    for ((expected_slug, relative), outcome) in documents.iter().zip(outcomes) {
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
        if identity != *expected_slug {
            return Err(format!(
                "{}: expected document slug {}, Pandoc emitted {}",
                relative.display(), expected_slug, identity
            ).into());
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
            "extra":{"filename_hint":relative.file_name().and_then(|name| name.to_str()).unwrap_or(expected_slug),
            "source_path":relative.to_string_lossy().replace('\\',"/"),"metadata":metadata}}));
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
    let ledger = git::append_inflight_snapshot(&repository, &LedgerSnapshotRequest {
        dispatch: DispatchId(dispatch.clone()),
        plan: PlanId(input.plan.clone()),
        sources: ledger_sources.clone(),
    })?;
    let source_rows = ledger_sources.iter().zip(ledger.blobs.iter()).map(|(source, (path, blob))| {
        (source.slug.clone(), path.to_string_lossy().into_owned(), blob.clone())
    }).collect::<Vec<_>>();
    db::record_inflight(
        &database, &dispatch, &input.plan, &ledger.reference, &ledger.commit.0, &source_rows,
    )?;
    run_asc(&asc, ["upload", "calls"], &ndjson(&calls)?)?;
    run_asc(&asc, ["enqueue"], &ndjson(&enqueue)?)?;
    ensure_runtime_daemons(&asc)?;
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

fn configured_pandoc_binary() -> Result<PathBuf, Box<dyn std::error::Error>> {
    let path = env::var_os("PANDOC_BIN").map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/usr/bin/pandoc"));
    if !path.is_absolute() { return Err("PANDOC_BIN must be absolute".into()); }
    Ok(path)
}

fn configured_pandoc_filter() -> Result<PathBuf, Box<dyn std::error::Error>> {
    let path = env::var_os("AUTOSCRIBE_PANDOC_FILTER").map(PathBuf::from)
        .ok_or("AUTOSCRIBE_PANDOC_FILTER is not set")?;
    if !path.is_absolute() { return Err("AUTOSCRIBE_PANDOC_FILTER must be absolute".into()); }
    Ok(path)
}

fn configured_pandoc_parallelism() -> usize {
    env::var("AUTOSCRIBE_PANDOC_PARALLELISM").ok()
        .and_then(|value| value.parse().ok()).filter(|value| *value >= 2)
        .unwrap_or_else(|| std::thread::available_parallelism().map(usize::from).unwrap_or(2).max(2))
}

fn require_plan_slug(snapshot: &serde_json::Value, plan: &str) -> Result<(), Box<dyn std::error::Error>> {
    let plans = snapshot.pointer("/registries/plans").ok_or("control snapshot has no plans registry")?;
    let found = match plans {
        serde_json::Value::Object(records) => records.iter().any(|(key, record)| {
            key == plan || ["record_identity", "slug", "key"].into_iter()
                .any(|field| record.get(field).and_then(serde_json::Value::as_str) == Some(plan))
        }),
        serde_json::Value::Array(records) => records.iter().any(|record| {
            ["record_identity", "slug", "key"].into_iter()
                .any(|field| record.get(field).and_then(serde_json::Value::as_str) == Some(plan))
        }),
        _ => false,
    };
    if found { Ok(()) } else { Err(format!("plan slug is not available: {plan}").into()) }
}

fn resolve_document_slugs(repository: &Path, requested: &[String]) -> Result<Vec<(String, PathBuf)>, Box<dyn std::error::Error>> {
    let mut wanted = std::collections::BTreeSet::new();
    for slug in requested {
        let slug = slug.trim();
        if slug.is_empty() { return Err("document slug cannot be blank".into()); }
        if !wanted.insert(slug.to_string()) { return Err(format!("duplicate document slug: {slug}").into()); }
    }
    let mut matches = std::collections::BTreeMap::<String, Vec<PathBuf>>::new();
    scan_markdown_slugs(repository, repository, &wanted, &mut matches)?;
    let mut resolved = Vec::new();
    for slug in wanted {
        match matches.remove(&slug).unwrap_or_default().as_slice() {
            [] => return Err(format!("document slug was not found: {slug}").into()),
            [path] => resolved.push((slug, path.clone())),
            paths => return Err(format!("document slug is duplicated: {slug}: {}",
                paths.iter().map(|path| path.display().to_string()).collect::<Vec<_>>().join(", ")).into()),
        }
    }
    Ok(resolved)
}

fn scan_markdown_slugs(
    repository: &Path,
    directory: &Path,
    wanted: &std::collections::BTreeSet<String>,
    matches: &mut std::collections::BTreeMap<String, Vec<PathBuf>>,
) -> Result<(), Box<dyn std::error::Error>> {
    const SKIP: &[&str] = &[".git", ".obsidian", ".trash", "_control", "node_modules", "target"];
    for entry in std::fs::read_dir(directory)? {
        let entry = entry?;
        let file_type = entry.file_type()?;
        let name = entry.file_name();
        let name = name.to_string_lossy();
        if file_type.is_dir() {
            if !SKIP.contains(&name.as_ref()) { scan_markdown_slugs(repository, &entry.path(), wanted, matches)?; }
            continue;
        }
        if !file_type.is_file() || entry.path().extension().and_then(|value| value.to_str()) != Some("md") { continue; }
        let text = match std::fs::read_to_string(entry.path()) { Ok(text) => text, Err(_) => continue };
        let Some(slug) = markdown_slug(&text) else { continue; };
        if wanted.contains(&slug) {
            matches.entry(slug).or_default().push(entry.path().strip_prefix(repository)?.to_path_buf());
        }
    }
    Ok(())
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
    let server = reconcile_authored_catalog(&db, &asc_command())?;
    Ok(DefinePlanSnapshotOutput {
        ok: true,
        operation: "define-plan.snapshot",
        server,
        authored_plans: plan_repository::list(&db, "plans")?,
        authored_instructions: plan_repository::list(&db, "instructions")?,
    })
}

fn reconcile_authored_catalog(
    db: &Database,
    asc: &Path,
) -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let snapshot = || -> Result<serde_json::Value, Box<dyn std::error::Error>> {
        Ok(serde_json::from_slice(&run_asc_capture(asc, ["control", "snapshot"], &[])?)?)
    };
    let server = snapshot()?;
    let authored_instructions = plan_repository::list(db, "instructions")?;
    let authored_plans = plan_repository::list(db, "plans")?;
    let upload = reconcile::authored_catalog(&server, authored_instructions, authored_plans);
    let changed = !upload.instructions.is_empty() || !upload.plans.is_empty();
    if !upload.instructions.is_empty() {
        run_asc(asc, ["upload", "instructions"], &ndjson(&upload.instructions)?)?;
    }
    if !upload.plans.is_empty() {
        run_asc(asc, ["upload", "plans"], &ndjson(&upload.plans)?)?;
    }
    if changed { snapshot() } else { Ok(server) }
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
            message: format!("could not start {}: {error}", asc.display()),
        })?;
    if let Some(mut stdin) = child.stdin.take() {
        use std::io::Write;
        stdin.write_all(input).map_err(|error| AscFailure {
            message: format!("could not stream payload to {}: {error}", asc.display()),
        })?;
    }
    let output = child.wait_with_output().map_err(|error| AscFailure {
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
            message: format!(
                "{} exited with {}: {}",
                asc.display(),
                output.status,
                detail.trim()
            ),
        })
    }
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

fn ensure_runtime_daemons(asc: &Path) -> Result<(), AscFailure> {
    let status = run_asc_capture(asc, ["run", "status"], &[]);
    let needs_start = match status {
        Ok(output) => {
            let text = String::from_utf8_lossy(&output);
            text.lines().any(|line| {
                line.contains("=not-running")
                    || line.contains("=stale")
                    || line.contains("=crashed")
            })
        }
        Err(_) => true,
    };
    if needs_start {
        run_asc(asc, ["run", "start"], &[])?;
    }
    Ok(())
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
            message: format!("could not start {}: {error}", asc.display()),
        })?;
    if let Some(mut stdin) = child.stdin.take() {
        use std::io::Write;
        stdin.write_all(input).map_err(|error| AscFailure {
            message: format!("could not stream payload to {}: {error}", asc.display()),
        })?;
    }
    let output = child.wait_with_output().map_err(|error| AscFailure {
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
        message: format!(
            "{} exited with {}: {}",
            asc.display(),
            output.status,
            detail.trim()
        ),
    })
}
