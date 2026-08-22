use autoscribe_service::{
    Service,
    db::{self, Database},
    git, instruction_sync,
    pandoc, plan_repository, response_repository,
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
    plan: serde_json::Value,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct InstructionSyncInput {
    version: u32,
    slugs: Vec<String>,
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
    catalogs: serde_json::Value,
    refreshed_at: Option<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CatalogRefreshInput {
    version: u32,
    #[serde(default)]
    instruction_slugs: Vec<String>,
}

#[derive(Serialize)]
struct CatalogRefreshOutput {
    ok: bool,
    operation: &'static str,
    catalogs: serde_json::Value,
    refreshed_at: String,
    uploaded_instructions: usize,
    committed_instructions: usize,
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
struct ResolveSlugsInput {
    version: u32,
    slugs: Vec<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct VersionInput { version:u32 }
fn main() -> ExitCode {
    match env::args().nth(1).as_deref() {
        Some("dispatch-run") => return dispatch_run(),
        Some("define-plan-snapshot") => return define_plan_snapshot(),
        Some("define-plan-refresh") => return command_output("define-plan.refresh", catalog_refresh_from_stdin("define-plan.refresh")),
        Some("dispatch-refresh") => return command_output("dispatch.refresh", catalog_refresh_from_stdin("dispatch.refresh")),
        Some("system-snapshot") => return command_output("system.snapshot", system_snapshot_from_stdin()),
        Some("resolve-slugs") => return command_output("slugs.resolve", resolve_slugs_from_stdin()),
        Some("plan-save") => return plan_save(),
        Some("instructions-state-snapshot") => return command_output("instructions.state-snapshot", instructions_state_snapshot_from_stdin()),
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

fn runtime_active_call_count(asc: &Path) -> Result<usize, Box<dyn std::error::Error>> {
    let output = run_asc_capture(asc, ["run", "status"], &[])?;
    let text = std::str::from_utf8(&output)?;
    let mut in_active_calls = false;
    let mut saw_section = false;
    let mut count = 0usize;
    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed == "active_calls:" {
            in_active_calls = true;
            saw_section = true;
            continue;
        }
        if !in_active_calls { continue; }
        if trimmed == "inboxes:" { break; }
        if trimmed.is_empty() || trimmed == "none" { continue; }
        if trimmed.contains(" score=") { count += 1; }
    }
    if !saw_section { return Err("asc run status did not contain active_calls section".into()); }
    Ok(count)
}

fn system_snapshot_from_stdin() -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let input: VersionInput = read_json_stdin()?;
    if input.version != 1 { return Err("unsupported system snapshot version".into()); }
    let repository = git::root(&std::env::current_dir()?)?;
    let db = open_database(&configured_database_path()?)?;
    let mut pipeline = serde_json::to_value(db::system_counts(&db)?)?;
    let runtime_active_calls = runtime_active_call_count(&asc_command())?;
    if let Some(object) = pipeline.as_object_mut() {
        object.insert("runtime_active_calls".into(), runtime_active_calls.into());
        // inflight_dispatches is durable dispatch lineage, not runtime state.
        // Dashboard-facing active state must come from the runtime itself.
        object.insert("active_dispatches".into(), runtime_active_calls.into());
        object.insert("processing_calls".into(), runtime_active_calls.into());
    }
    Ok(serde_json::json!({
        "ok":true,
        "operation":"system.snapshot",
        "git":git::summary(&repository)?,
        "pipeline":pipeline
    }))
}

fn instruction_slug_candidates(repository: &Path) -> Result<std::collections::BTreeSet<String>, Box<dyn std::error::Error>> {
    let output = Command::new("rg")
        .args(["-l", "-0", "--glob", "*.md", r"^slug:\s*"])
        .current_dir(repository)
        .output()?;
    if !output.status.success() && output.status.code() != Some(1) {
        return Err(format!("rg instruction discovery failed with status {:?}: {}",
            output.status.code(), String::from_utf8_lossy(&output.stderr).trim()).into());
    }
    let mut by_slug = std::collections::BTreeMap::<String, Vec<PathBuf>>::new();
    for raw in output.stdout.split(|byte| *byte == 0).filter(|value| !value.is_empty()) {
        let relative = PathBuf::from(std::str::from_utf8(raw)?);
        let absolute = repository.join(&relative);
        let text = std::fs::read_to_string(&absolute)?;
        let declared = ["record", "type", "kind"].into_iter()
            .find_map(|key| markdown_frontmatter_value(&text, key))
            .unwrap_or_default().to_lowercase();
        if declared != "instruction" { continue; }
        let Some(slug) = markdown_frontmatter_value(&text, "slug") else { continue; };
        by_slug.entry(slug).or_default().push(relative);
    }
    let duplicates = by_slug.iter().filter(|(_, paths)| paths.len() > 1)
        .map(|(slug, paths)| format!("{slug}: {}", paths.iter().map(|p| p.display().to_string()).collect::<Vec<_>>().join(", ")))
        .collect::<Vec<_>>();
    if !duplicates.is_empty() {
        return Err(format!("duplicate instruction slugs: {}", duplicates.join("; ")).into());
    }
    Ok(by_slug.into_keys().collect())
}

fn instruction_record_slug(value: &serde_json::Value) -> String {
    ["slug", "record_identity", "identity", "key"].into_iter()
        .find_map(|field| value.get(field).and_then(serde_json::Value::as_str))
        .unwrap_or("").trim().to_string()
}

fn instructions_state_snapshot_from_stdin() -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let input: VersionInput = read_json_stdin()?;
    if input.version != 1 { return Err("unsupported instructions state snapshot version".into()); }
    let repository = git::root(&std::env::current_dir()?)?;
    let slugs = instruction_slug_candidates(&repository)?;
    let local = instruction_sync::scan_slugs(&repository, &slugs)?;
    let manifest: serde_json::Value = serde_json::from_slice(&run_asc_capture(
        &asc_command(), ["control", "instruction-manifest"], &[],
    )?)?;
    let sync = instruction_sync::plan(local, &manifest)?;

    let server = fetch_server_snapshot(&asc_command())?;
    let db = open_configured_database()?;
    let refreshed_at = unix_timestamp();
    cache_server_snapshot(&db, &server, &refreshed_at)?;
    let server_catalog = catalogs_from_server(&server);
    let remote_slugs = server_catalog.get("instructions").and_then(serde_json::Value::as_array)
        .into_iter().flatten().map(instruction_record_slug).filter(|slug| !slug.is_empty())
        .collect::<std::collections::BTreeSet<_>>();

    let upload_slugs = sync.upload.iter()
        .map(instruction_sync::upload_record)
        .map(|value| instruction_record_slug(&value))
        .filter(|slug| !slug.is_empty())
        .collect::<std::collections::BTreeSet<_>>();
    let mut items = Vec::new();
    for item in &sync.items {
        let mut value = serde_json::to_value(item)?;
        let slug = instruction_record_slug(&value);
        if let Some(object) = value.as_object_mut() {
            object.insert("remote".into(), serde_json::Value::String(
                if remote_slugs.contains(&slug) { "present" } else { "missing" }.into()
            ));
            object.insert("needs_upload".into(), serde_json::Value::Bool(upload_slugs.contains(&slug)));
        }
        items.push(value);
    }
    Ok(serde_json::json!({
        "ok": true,
        "operation": "instructions.state-snapshot",
        "items": items,
        "refreshed_at": refreshed_at,
        "hashes_compared": sync.hashes_compared,
        "upload_needed": upload_slugs.len()
    }))
}

fn instructions_sync_from_stdin() -> Result<InstructionSyncOutput, Box<dyn std::error::Error>> {
    let input: InstructionSyncInput = read_json_stdin()?;
    if input.version != 1 { return Err("unsupported instruction sync version".into()); }
    let repository = git::root(&std::env::current_dir()?)?;
    let selected = input.slugs.into_iter().map(|slug| slug.trim().to_string())
        .filter(|slug| !slug.is_empty()).collect::<std::collections::BTreeSet<_>>();
    if selected.is_empty() { return Err("instruction sync requires selected slugs".into()); }
    let local = instruction_sync::scan_slugs(&repository, &selected)?;
    let resolved = local.iter()
        .map(instruction_sync::upload_record)
        .map(|value| instruction_record_slug(&value))
        .filter(|slug| !slug.is_empty())
        .collect::<std::collections::BTreeSet<_>>();
    if resolved != selected {
        let missing = selected.difference(&resolved).cloned().collect::<Vec<_>>();
        return Err(format!("selected instruction slugs were not found: {}", missing.join(", ")).into());
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
        scanned: selected.len(),
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

fn markdown_frontmatter_value(text: &str, key: &str) -> Option<String> {
    let mut lines = text.lines();
    if lines.next().map(str::trim) != Some("---") { return None; }
    let prefix = format!("{key}:");
    for line in lines {
        if line.trim() == "---" { break; }
        if line.chars().next().is_some_and(char::is_whitespace) { continue; }
        if let Some(value) = line.strip_prefix(&prefix) {
            let value = value.trim().trim_matches(['\'', '"']);
            return (!value.is_empty()).then(|| value.to_string());
        }
    }
    None
}

fn markdown_slug(text: &str) -> Option<String> {
    markdown_frontmatter_value(text, "slug")
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
    require_plan_available(&database, &input.plan)?;
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

fn require_plan_available(db: &Database, plan: &str) -> Result<(), Box<dyn std::error::Error>> {
    if plan_repository::list(db)?.iter().any(|record| {
        ["record_identity", "slug"].into_iter().any(|field| record.get(field).and_then(serde_json::Value::as_str) == Some(plan))
    }) { return Ok(()); }
    let cached = cached_server_snapshot(db)?;
    let catalogs = catalogs_from_server(&cached);
    let found = catalogs.get("plans").and_then(serde_json::Value::as_array).is_some_and(|records| {
        records.iter().any(|record| ["record_identity", "slug", "key"].into_iter()
            .any(|field| record.get(field).and_then(serde_json::Value::as_str) == Some(plan)))
    });
    if found { Ok(()) } else { Err(format!("plan slug is not available in service state: {plan}").into()) }
}

fn resolve_slugs_from_stdin() -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let input: ResolveSlugsInput = read_json_stdin()?;
    if input.version != 1 { return Err("unsupported slug resolver version".into()); }
    let repository = git::root(&std::env::current_dir()?)?;
    let mut wanted = std::collections::BTreeSet::new();
    for raw in input.slugs {
        let slug = raw.trim();
        if slug.is_empty() { continue; }
        wanted.insert(slug.to_string());
    }
    let matches = instruction_sync::resolve_slug_paths(&repository, &wanted)?;
    let mut items = Vec::new();
    for slug in wanted {
        match matches.get(&slug).map(Vec::as_slice).unwrap_or(&[]) {
            [] => items.push(serde_json::json!({"slug":slug,"status":"missing"})),
            [path] => items.push(serde_json::json!({
                "slug":slug,
                "status":"found",
                "path":path.to_string_lossy().replace('\\', "/")
            })),
            paths => return Err(format!("slug is duplicated: {slug}: {}",
                paths.iter().map(|path| path.display().to_string()).collect::<Vec<_>>().join(", ")).into()),
        }
    }
    Ok(serde_json::json!({"ok":true,"operation":"slugs.resolve","items":items}))
}

fn resolve_document_slugs(repository: &Path, requested: &[String]) -> Result<Vec<(String, PathBuf)>, Box<dyn std::error::Error>> {
    let mut wanted = std::collections::BTreeSet::new();
    for slug in requested {
        let slug = slug.trim();
        if slug.is_empty() { return Err("document slug cannot be blank".into()); }
        if !wanted.insert(slug.to_string()) { return Err(format!("duplicate document slug: {slug}").into()); }
    }
    let matches = instruction_sync::resolve_slug_paths(repository, &wanted)?;
    let mut resolved = Vec::new();
    for slug in wanted {
        match matches.get(&slug).map(Vec::as_slice).unwrap_or(&[]) {
            [] => return Err(format!("document slug was not found: {slug}").into()),
            [path] => resolved.push((slug, path.clone())),
            paths => return Err(format!("document slug is duplicated: {slug}: {}",
                paths.iter().map(|path| path.display().to_string()).collect::<Vec<_>>().join(", ")).into()),
        }
    }
    Ok(resolved)
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

const CATALOG_SNAPSHOT_KEY: &str = "catalog.snapshot";
const CATALOG_REFRESHED_AT_KEY: &str = "catalog.refreshed_at";

fn define_plan_snapshot() -> ExitCode {
    command_output("define-plan.snapshot", snapshot_from_service())
}

fn snapshot_from_service() -> Result<DefinePlanSnapshotOutput, Box<dyn std::error::Error>> {
    let repository = git::root(&std::env::current_dir()?)?;
    let db = open_configured_database()?;
    let server = cached_server_snapshot(&db)?;
    Ok(DefinePlanSnapshotOutput {
        ok: true,
        operation: "define-plan.snapshot",
        catalogs: catalogs_with_authored_plans(&db, &server, &repository)?,
        refreshed_at: db::meta_get(&db, CATALOG_REFRESHED_AT_KEY)?,
    })
}

fn catalog_refresh_from_stdin(operation: &'static str) -> Result<CatalogRefreshOutput, Box<dyn std::error::Error>> {
    let input: CatalogRefreshInput = read_json_stdin()?;
    if input.version != 1 { return Err("unsupported catalog refresh version".into()); }
    let repository = git::root(&std::env::current_dir()?)?;
    let db = open_configured_database()?;
    let asc = asc_command();
    let (server, uploaded, committed) = refresh_catalog(&repository, &asc, &input.instruction_slugs)?;
    let refreshed_at = unix_timestamp();
    cache_server_snapshot(&db, &server, &refreshed_at)?;
    Ok(CatalogRefreshOutput {
        ok: true,
        operation,
        catalogs: catalogs_with_authored_plans(&db, &server, &repository)?,
        refreshed_at,
        uploaded_instructions: uploaded,
        committed_instructions: committed,
    })
}

fn open_configured_database() -> Result<Database, Box<dyn std::error::Error>> {
    let database_path = configured_database_path()?;
    if let Some(parent) = database_path.parent() { std::fs::create_dir_all(parent)?; }
    let db = Database::open_path(&database_path)?;
    db::migrate(&db)?;
    Ok(db)
}

fn cached_server_snapshot(db: &Database) -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    Ok(match db::meta_get(db, CATALOG_SNAPSHOT_KEY)? {
        Some(text) => serde_json::from_str(&text)?,
        None => serde_json::json!({"registries":{}}),
    })
}

fn cache_server_snapshot(db: &Database, snapshot: &serde_json::Value, refreshed_at: &str) -> Result<(), Box<dyn std::error::Error>> {
    db::meta_set_many(db, &[
        (CATALOG_SNAPSHOT_KEY, serde_json::to_string(snapshot)?),
        (CATALOG_REFRESHED_AT_KEY, refreshed_at.to_string()),
    ])?;
    Ok(())
}

fn refresh_catalog(repository: &Path, asc: &Path, instruction_slugs: &[String]) -> Result<(serde_json::Value, usize, usize), Box<dyn std::error::Error>> {
    let mut server = fetch_server_snapshot(asc)?;
    let mut uploaded = 0;
    let mut committed = 0;
    let requested = instruction_slugs.iter().map(|slug| slug.trim()).filter(|slug| !slug.is_empty())
        .map(str::to_string).collect::<std::collections::BTreeSet<_>>();
    if !requested.is_empty() {
        let local = instruction_sync::scan_slugs(repository, &requested)?;
        let manifest: serde_json::Value = serde_json::from_slice(&run_asc_capture(asc, ["control", "instruction-manifest"], &[])?)?;
        let sync = instruction_sync::plan(local, &manifest)?;
        uploaded = sync.upload.len();
        if !sync.upload.is_empty() {
            let records = sync.upload.iter().map(instruction_sync::upload_record).collect::<Vec<_>>();
            run_asc(asc, ["upload", "instructions"], &ndjson(&records)?)?;
            let paths = sync.upload.iter().map(|item| PathBuf::from(&item.relative_path)).collect::<Vec<_>>();
            let dirty = git::inspect(repository, &paths)?.into_iter().filter(|item| item.dirty).map(|item| item.path).collect::<Vec<_>>();
            if !dirty.is_empty() {
                git::commit(repository, CommitRequest { paths: dirty.clone(), message: "Sync local instructions".into(), purpose: CommitPurpose::Version })?;
                committed = dirty.len();
            }
            server = fetch_server_snapshot(asc)?;
        }
    }
    Ok((server, uploaded, committed))
}

fn fetch_server_snapshot(asc: &Path) -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let control: serde_json::Value =
        serde_json::from_slice(&run_asc_capture(asc, ["control", "snapshot"], &[])?)?;
    if !control.is_object() {
        return Err("control snapshot must be an object".into());
    }
    Ok(control)
}

fn catalogs_with_authored_plans(
    db: &Database,
    server: &serde_json::Value,
    repository: &Path,
) -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let mut catalogs = catalogs_from_server(server);

    let authored = plan_repository::list(db)?;
    let mut referenced_instructions = std::collections::BTreeSet::<String>::new();
    for plan in &authored {
        referenced_instructions.extend(plan_instruction_slugs(plan));
    }

    {
        let instructions = catalogs.get_mut("instructions")
            .and_then(serde_json::Value::as_array_mut)
            .ok_or("catalog instructions must be an array")?;
        overlay_local_plan_instructions(repository, instructions, &referenced_instructions)?;
    }

    let plans = catalogs.get_mut("plans")
        .and_then(serde_json::Value::as_array_mut)
        .ok_or("catalog plans must be an array")?;
    let mut by_slug = std::collections::BTreeMap::<String, serde_json::Value>::new();
    for plan in plans.drain(..) {
        let slug = ["record_identity", "slug", "key"].into_iter()
            .find_map(|field| plan.get(field).and_then(serde_json::Value::as_str))
            .unwrap_or("").to_string();
        if !slug.is_empty() { by_slug.insert(slug, plan); }
    }
    for plan in authored {
        let slug = ["record_identity", "slug"].into_iter()
            .find_map(|field| plan.get(field).and_then(serde_json::Value::as_str))
            .unwrap_or("").to_string();
        if !slug.is_empty() { by_slug.insert(slug, plan); }
    }
    plans.extend(by_slug.into_values());
    Ok(catalogs)
}

fn overlay_local_plan_instructions(
    repository: &Path,
    instructions: &mut Vec<serde_json::Value>,
    referenced: &std::collections::BTreeSet<String>,
) -> Result<(), Box<dyn std::error::Error>> {
    if referenced.is_empty() { return Ok(()); }

    let mut present = instructions.iter().filter_map(|record| {
        ["slug", "record_identity", "identity", "key"].into_iter()
            .find_map(|field| record.get(field).and_then(serde_json::Value::as_str))
            .map(str::trim).filter(|value| !value.is_empty()).map(str::to_string)
    }).collect::<std::collections::BTreeSet<_>>();

    let missing = referenced.difference(&present).cloned()
        .collect::<std::collections::BTreeSet<_>>();
    if missing.is_empty() { return Ok(()); }

    // resolve_slug_paths is the Rust/rg boundary: resolve only the exact slugs
    // referenced by durable local plans. Do not walk the vault.
    let resolved = instruction_sync::resolve_slug_paths(repository, &missing)?;
    for slug in missing {
        match resolved.get(&slug).map(Vec::as_slice).unwrap_or(&[]) {
            [path] => {
                instructions.push(local_instruction_catalog_record(repository, path, &slug)?);
                present.insert(slug);
            }
            [] => {
                // Keep the plan legible even when its source has genuinely gone.
                // Save/dispatch remains responsible for refusing an unavailable slug.
                instructions.push(serde_json::json!({
                    "slug": slug,
                    "title": format!("{} (unavailable)", slug),
                    "component": instruction_component_from_slug(&slug),
                    "scope": "local",
                    "unavailable": true,
                    "source": "local-plan-reference"
                }));
            }
            paths => return Err(format!(
                "instruction slug is duplicated: {slug}: {}",
                paths.iter().map(|path| path.display().to_string()).collect::<Vec<_>>().join(", ")
            ).into()),
        }
    }
    Ok(())
}

fn local_instruction_catalog_record(
    repository: &Path,
    relative: &Path,
    slug: &str,
) -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let path = if relative.is_absolute() { relative.to_path_buf() } else { repository.join(relative) };
    let text = std::fs::read_to_string(&path)?;
    if markdown_slug(&text).as_deref() != Some(slug) {
        return Err(format!("resolved instruction does not contain expected slug {slug}: {}", relative.display()).into());
    }
    let title = markdown_frontmatter_scalar(&text, "title").unwrap_or_else(|| slug.to_string());
    let component = markdown_frontmatter_scalar(&text, "component")
        .or_else(|| markdown_frontmatter_scalar(&text, "class"))
        .map(|value| match value.as_str() {
            "instruction" | "specific" => "task".to_string(),
            "reference" => "rule".to_string(),
            _ => value,
        })
        .unwrap_or_else(|| instruction_component_from_slug(slug));
    Ok(serde_json::json!({
        "slug": slug,
        "title": title,
        "component": component,
        "scope": "local",
        "path": relative.to_string_lossy().replace('\\', "/"),
        "source": "local-plan-reference"
    }))
}

fn markdown_frontmatter_scalar(text: &str, wanted: &str) -> Option<String> {
    let mut lines = text.lines();
    if lines.next().map(str::trim) != Some("---") { return None; }
    let prefix = format!("{wanted}:");
    for line in lines {
        let trimmed = line.trim();
        if trimmed == "---" { break; }
        if line.chars().next().is_some_and(char::is_whitespace) { continue; }
        if let Some(value) = line.strip_prefix(&prefix) {
            let value = value.trim().trim_matches(['\'', '"']);
            if !value.is_empty() && value != "null" && value != "~" {
                return Some(value.to_string());
            }
        }
    }
    None
}

fn instruction_component_from_slug(slug: &str) -> String {
    match slug.split('.').next().unwrap_or("") {
        "std" => "standing",
        "rul" | "ref" => "rule",
        "rol" => "role",
        "ctx" => "context",
        "tsk" | "ins" | "spc" => "task",
        _ => "",
    }.to_string()
}

fn catalogs_from_server(server: &serde_json::Value) -> serde_json::Value {
    let registries = server.get("registries").and_then(serde_json::Value::as_object);
    let list = |name: &str| registry_records(registries.and_then(|all| all.get(name)), name == "instructions");
    serde_json::json!({
        "instructions": list("instructions"),
        "plans": list("plans"),
        "engines": list("engines"),
        "models": list("models"),
        "scripts": list("local_scripts"),
        "rag_profiles": list("rag_profiles"),
    })
}

fn registry_records(value: Option<&serde_json::Value>, instructions: bool) -> Vec<serde_json::Value> {
    let mut records = Vec::new();
    match value {
        Some(serde_json::Value::Object(map)) => for (key, value) in map {
            let mut record = value.as_object().cloned().unwrap_or_default();
            record.entry("key").or_insert_with(|| serde_json::Value::String(key.clone()));
            if instructions { normalize_instruction_record(&mut record, key); }
            records.push(serde_json::Value::Object(record));
        },
        Some(serde_json::Value::Array(values)) => for value in values {
            let mut record = value.as_object().cloned().unwrap_or_default();
            let key = ["slug", "record_identity", "key"].into_iter().find_map(|field| record.get(field).and_then(serde_json::Value::as_str)).unwrap_or("").to_string();
            if instructions { normalize_instruction_record(&mut record, &key); }
            records.push(serde_json::Value::Object(record));
        },
        _ => {}
    }
    records
}

fn normalize_instruction_record(record: &mut serde_json::Map<String, serde_json::Value>, fallback: &str) {
    let slug = ["slug", "record_identity", "identity", "key"].into_iter()
        .find_map(|field| record.get(field).and_then(serde_json::Value::as_str)).filter(|value| !value.trim().is_empty())
        .unwrap_or(fallback).to_string();
    let extra_scope = record.get("extra").and_then(serde_json::Value::as_object)
        .and_then(|x| x.get("scope")).and_then(serde_json::Value::as_str).map(str::to_string);
    let extra_component = record.get("extra").and_then(serde_json::Value::as_object)
        .and_then(|x| x.get("component")).and_then(serde_json::Value::as_str).map(str::to_string);
    let extra_title = record.get("extra").and_then(serde_json::Value::as_object)
        .and_then(|x| x.get("title")).and_then(serde_json::Value::as_str).map(str::to_string);
    let scope = record.get("scope").and_then(serde_json::Value::as_str).map(str::to_string)
        .or(extra_scope)
        .or_else(|| record.get("component").and_then(serde_json::Value::as_str).map(str::to_string))
        .or(extra_component)
        .unwrap_or_else(|| match slug.split('.').next().unwrap_or("") { "std"=>"standing", "rol"=>"role", "ctx"=>"context", "tsk"=>"task", _=>"" }.to_string());
    let title = record.get("title").and_then(serde_json::Value::as_str).map(str::to_string)
        .or(extra_title).unwrap_or_else(|| slug.clone());
    record.insert("slug".into(), serde_json::Value::String(slug));
    record.insert("scope".into(), serde_json::Value::String(scope));
    record.insert("title".into(), serde_json::Value::String(title));
}

fn unix_timestamp() -> String {
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|value| value.as_secs().to_string()).unwrap_or_else(|_| "0".into())
}

fn plan_instruction_slugs(plan: &serde_json::Value) -> std::collections::BTreeSet<String> {
    let mut out = std::collections::BTreeSet::new();
    if let Some(steps) = plan.pointer("/payload/steps").and_then(serde_json::Value::as_object) {
        for step in steps.values() {
            if let Some(groups) = step.get("instruction_slugs").and_then(serde_json::Value::as_object) {
                for values in groups.values().filter_map(serde_json::Value::as_array) {
                    for slug in values.iter().filter_map(serde_json::Value::as_str).map(str::trim).filter(|s| !s.is_empty()) { out.insert(slug.to_string()); }
                }
            }
            if let Some(slug) = step.get("instruction").and_then(serde_json::Value::as_str).map(str::trim).filter(|s| !s.is_empty()) { out.insert(slug.to_string()); }
        }
    }
    out
}

fn plan_save() -> ExitCode {
    command_output("plan.save", save_plan_from_stdin())
}

fn save_plan_from_stdin() -> Result<PlanSaveOutput, Box<dyn std::error::Error>> {
    let input: PlanSaveInput = read_json_stdin()?;
    if input.version != 1 { return Err(format!("unsupported plan save version: {}", input.version).into()); }
    let repository = git::root(&std::env::current_dir()?)?;
    let db = open_configured_database()?;
    let asc = asc_command();
    let slugs = plan_instruction_slugs(&input.plan).into_iter().collect::<Vec<_>>();
    let (_, uploaded, _) = refresh_catalog(&repository, &asc, &slugs)?;
    plan_repository::save(&db, &input.plan)?;
    let identity = input.plan.get("record_identity").and_then(serde_json::Value::as_str)
        .ok_or("saved plan is missing record_identity")?.to_string();
    let plan_upload = serde_json::json!({"type":"plan","identity":identity.clone(),"content":input.plan["payload"],"extra":{}});
    run_asc(&asc, ["upload", "plans"], &ndjson(&[plan_upload])?)?;
    let server = fetch_server_snapshot(&asc)?;
    let refreshed_at = unix_timestamp();
    cache_server_snapshot(&db, &server, &refreshed_at)?;
    Ok(PlanSaveOutput { ok: true, operation: "plan.save", plan: identity, instructions: uploaded })
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
