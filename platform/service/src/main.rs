use autoscribe_service::{
    db::{self, Database},
    git, instruction_sync,
    pandoc, plan_repository, response_repository,
    types::{CommitPurpose, CommitRequest, DispatchId, LedgerSnapshotRequest,
        LedgerSource, PandocJob, PlanId, VersionRequest},
};
use serde::{Deserialize, Serialize};
use std::{
    env,
    fs::OpenOptions,
    io::{self, Read, Write},
    path::{Path, PathBuf},
    process::{Command, ExitCode, Stdio},
    time::Duration,
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
    #[serde(default)]
    dispatch_identity: Option<String>,
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

#[derive(Serialize)]
struct DefinePlanSnapshotOutput {
    ok: bool,
    operation: &'static str,
    catalogs: serde_json::Value,
    refreshed_at: Option<String>,
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

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct WriteResponsesInput {
    version: u32,
    #[serde(default = "default_apply_write_responses")]
    apply: bool,
}

fn default_apply_write_responses() -> bool { true }
fn main() -> ExitCode {
    match env::args().nth(1).as_deref() {
        Some("__dispatch-run") => return dispatch_run(),
        Some("watch-dispatch") => return watch_dispatch(),
        Some("refresh") => return command_output("refresh", refresh_cli()),
        Some("define-plan-snapshot") => return define_plan_snapshot(),
        Some("system-snapshot") => return command_output("system.snapshot", system_snapshot_from_stdin()),
        Some("resolve-slugs") => return command_output("slugs.resolve", resolve_slugs_from_stdin()),
        Some("git-files") => return command_output("git.files", git_files_from_stdin()),
        Some("write-responses") => return write_responses(),
        _ => {
            eprintln!("usage: svc watch-dispatch [--once] | refresh | write-responses | system-snapshot | git-files");
            return ExitCode::FAILURE;
        }
    }
}

struct WatcherLock {
    path: PathBuf,
}

impl Drop for WatcherLock {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.path);
    }
}

fn acquire_watcher_lock(repository: &Path, name: &str) -> Result<WatcherLock, Box<dyn std::error::Error>> {
    let directory = autoscribe_state_dir(repository);
    std::fs::create_dir_all(&directory)?;
    let path = directory.join(format!("{name}.pid"));
    loop {
        match OpenOptions::new().write(true).create_new(true).open(&path) {
            Ok(mut file) => {
                writeln!(file, "{}", std::process::id())?;
                return Ok(WatcherLock { path });
            }
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {
                let pid = std::fs::read_to_string(&path).ok()
                    .and_then(|value| value.trim().parse::<u32>().ok());
                if pid.is_some_and(|pid| PathBuf::from(format!("/proc/{pid}")).exists()) {
                    return Err(format!("{name} is already running with pid {}", pid.unwrap()).into());
                }
                std::fs::remove_file(&path)?;
            }
            Err(error) => return Err(error.into()),
        }
    }
}

fn watcher_interval(name: &str, default_millis: u64) -> Result<Duration, Box<dyn std::error::Error>> {
    let millis = match env::var(name) {
        Ok(value) => value.parse::<u64>().map_err(|_| format!("{name} must be an integer number of milliseconds"))?,
        Err(env::VarError::NotPresent) => default_millis,
        Err(error) => return Err(error.into()),
    };
    if millis == 0 { return Err(format!("{name} must be greater than zero").into()); }
    Ok(Duration::from_millis(millis))
}

fn emit_watch_event(value: &serde_json::Value) {
    println!("{}", serde_json::to_string(value).expect("serializable watcher event"));
    let _ = io::stdout().flush();
}

fn watch_dispatch() -> ExitCode {
    let once = env::args().skip(2).any(|argument| argument == "--once");
    if env::args().skip(2).any(|argument| argument != "--once") {
        eprintln!("usage: svc watch-dispatch [--once]");
        return ExitCode::FAILURE;
    }
    let repository = match git::root(&std::env::current_dir().unwrap_or_default()) {
        Ok(repository) => repository,
        Err(error) => {
            emit_watch_event(&serde_json::json!({"ok":false,"operation":"watch-dispatch","error":error.to_string()}));
            return ExitCode::FAILURE;
        }
    };
    let result = (|| -> Result<ExitCode, Box<dyn std::error::Error>> {
        git::ensure_info_exclude(&repository, "/.autoscribe/")?;
        let _lock = acquire_watcher_lock(&repository, "watch-dispatch")?;
        let db = open_configured_database()?;
        let poll = watcher_interval("AUTOSCRIBE_DISPATCH_POLL_MS", 2_000)?;
        let retry = watcher_interval("AUTOSCRIBE_DISPATCH_RETRY_MS", 30_000)?;
        if !once {
            emit_watch_event(&serde_json::json!({
                "ok":true,
                "operation":"watch-dispatch.started",
                "repository":repository,
                "poll_ms":poll.as_millis(),
                "retry_ms":retry.as_millis()
            }));
        }
        loop {
            match reconcile_git_dispatch_commits(&repository, &db) {
                Ok(events) => {
                    if once {
                        emit_watch_event(&serde_json::json!({
                            "ok":true,"operation":"watch-dispatch.pass","events":events
                        }));
                        return Ok(ExitCode::SUCCESS);
                    }
                    for event in events {
                        emit_watch_event(&serde_json::json!({
                            "ok":true,"operation":"watch-dispatch.event","event":event
                        }));
                    }
                    std::thread::sleep(poll);
                }
                Err(error) => {
                    if once {
                        emit_watch_event(&serde_json::json!({
                            "ok":false,"operation":"watch-dispatch.pass","error":error.to_string()
                        }));
                        return Ok(ExitCode::FAILURE);
                    }
                    emit_watch_event(&serde_json::json!({
                        "ok":false,"operation":"watch-dispatch.retry","error":error.to_string(),
                        "retry_ms":retry.as_millis()
                    }));
                    std::thread::sleep(retry);
                }
            }
        }
    })();
    match result {
        Ok(code) => code,
        Err(error) => {
            emit_watch_event(&serde_json::json!({"ok":false,"operation":"watch-dispatch","error":error.to_string()}));
            ExitCode::FAILURE
        }
    }
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

fn instruction_record_slug(value: &serde_json::Value) -> String {
    ["slug", "record_identity", "identity", "key"].into_iter()
        .find_map(|field| value.get(field).and_then(serde_json::Value::as_str))
        .unwrap_or("").trim().to_string()
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
    let input: WriteResponsesInput = read_json_stdin()?;
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
        let outcome = if input.apply {
            apply_writeback(&repository, &db, record)
        } else {
            inspect_writeback_state(&repository, &db, &record)
        };
        match outcome {
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

fn response_record_identity(record: &serde_json::Value, field: &str) -> Result<String, Box<dyn std::error::Error>> {
    Ok(record.get(field).and_then(serde_json::Value::as_str)
        .map(str::trim).filter(|value| !value.is_empty())
        .ok_or_else(|| format!("pending response is missing {field}"))?.to_string())
}

fn resolve_writeback_target(
    repository: &Path,
    path: &str,
    source: &str,
) -> Result<(PathBuf, PathBuf, String), Box<dyn std::error::Error>> {
    let relative = PathBuf::from(path);
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
    if markdown_slug(&current).as_deref() != Some(source) {
        return Err(format!("current target slug does not match {source}: {path}").into());
    }
    Ok((relative, target, current))
}

fn target_git_state(
    repository: &Path,
    relative: &Path,
    dispatch_blob: &str,
) -> Result<(bool, bool), Box<dyn std::error::Error>> {
    let status = git::inspect(repository, &[relative.to_path_buf()])?
        .into_iter().next().ok_or("writeback target has no Git status")?;
    let current_blob = git::worktree_blob(repository, relative)?;
    Ok((status.dirty, current_blob == dispatch_blob))
}

fn ensure_response_snapshot(
    repository: &Path,
    db: &Database,
    record: &serde_json::Value,
    result: &str,
    source: &str,
    path: &str,
    dispatch_identity: &str,
    dispatch_commit: &str,
    stored_snapshot: Option<&str>,
) -> Result<(String, Vec<u8>), Box<dyn std::error::Error>> {
    let relative = PathBuf::from(path);
    if let Some(commit) = stored_snapshot {
        let bytes = git::read_version(repository, VersionRequest {
            revision: commit.to_string(),
            path: relative,
        })?;
        return Ok((commit.to_string(), bytes));
    }

    // Build the response candidate from the immutable dispatch source, never
    // from the current master file. A dirty/diverged master may contain human
    // changes that must not silently leak into the forensic response snapshot.
    let dispatch_bytes = git::read_version(repository, VersionRequest {
        revision: dispatch_commit.to_string(),
        path: relative.clone(),
    })?;
    let dispatch_source = String::from_utf8(dispatch_bytes)?;
    if markdown_slug(&dispatch_source).as_deref() != Some(source) {
        return Err(format!("dispatch source slug does not match {source}: {path}").into());
    }
    let response = record.get("content").and_then(serde_json::Value::as_str)
        .ok_or("pending response is missing content")?;
    let replacement = set_document_review_metadata(&preserve_frontmatter(&dispatch_source, response)?)?;
    let commit = git::append_response_snapshot(
        repository,
        dispatch_identity,
        result,
        source,
        "saved",
        &relative,
        replacement.as_bytes(),
    )?.0;
    response_repository::mark_forensic(db, result, &commit)?;
    Ok((commit, replacement.into_bytes()))
}

fn inspect_writeback_state(
    repository: &Path,
    db: &Database,
    record: &serde_json::Value,
) -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let result = response_record_identity(record, "result_identity")?;
    let source = response_record_identity(record, "source_identity")?;
    let path = response_record_identity(record, "source_path")?;
    let (state, dispatch_identity, dispatch_commit, source_blob, stored_outcome, _, stored_commit, stored_forensic) =
        response_repository::require_pending(db, &result, &source)?;
    let (relative, _, _) = resolve_writeback_target(repository, &path, &source)?;
    let (response_commit, _) = ensure_response_snapshot(
        repository, db, record, &result, &source, &path, &dispatch_identity, &dispatch_commit, stored_forensic.as_deref(),
    )?;
    let (dirty, matches_dispatch) = target_git_state(repository, &relative, &source_blob)?;
    let master_state = if dirty { "dirty" } else { "clean" };
    let source_state = if matches_dispatch { "matches-dispatch" } else { "changed-since-dispatch" };

    if state == "written" {
        if stored_outcome.as_deref() != Some("accepted") {
            return Err("response was already written with another outcome".into());
        }
        return Ok(serde_json::json!({
            "type":"writeback-result",
            "status":"written-pending-ack",
            "result_identity":result,
            "source_identity":source,
            "path":path,
            "master_state":master_state,
            "source_state":source_state,
            "inflight_commit":stored_commit.unwrap_or(response_commit),
            "decision_required":false
        }));
    }

    let (status, reason, decision_required) = if dirty {
        ("decision-required", "master-dirty", true)
    } else if !matches_dispatch {
        ("decision-required", "changed-since-dispatch", true)
    } else {
        ("ready", "ready", false)
    };
    Ok(serde_json::json!({
        "type":"writeback-result",
        "status":status,
        "result_identity":result,
        "source_identity":source,
        "path":path,
        "master_state":master_state,
        "source_state":source_state,
        "reason":reason,
        "inflight_commit":response_commit,
        "decision_required":decision_required
    }))
}

fn apply_writeback(
    repository: &Path,
    db: &Database,
    record: serde_json::Value,
) -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let result = response_record_identity(&record, "result_identity")?;
    let source = response_record_identity(&record, "source_identity")?;
    let path = response_record_identity(&record, "source_path")?;
    let (state, dispatch_identity, dispatch_commit, source_blob, stored_outcome, _, stored_commit, stored_forensic) =
        response_repository::require_pending(db, &result, &source)?;

    if state == "written" {
        if stored_outcome.as_deref() != Some("accepted") {
            return Err("response was already written with another outcome".into());
        }
        let commit = stored_commit.or(stored_forensic).ok_or("written response has no inflight response commit")?;
        run_asc(&asc_command(), ["export", "update-exports", result.as_str()], &[])?;
        response_repository::complete(db, &result)?;
        let relative = PathBuf::from(&path);
        let after_dirty = git::inspect(repository, std::slice::from_ref(&relative))?
            .into_iter().next().map(|status| status.dirty).unwrap_or(false);
        return Ok(serde_json::json!({
            "type":"writeback-result",
            "status":"written",
            "result_identity":result,
            "source_identity":source,
            "path":path,
            "master_state_before":"written-pending-ack",
            "master_state_after":if after_dirty {"dirty"} else {"clean"},
            "source_state":"recorded",
            "inflight_commit":commit,
            "document_status":"needs-review",
            "producer":"ai"
        }));
    }

    let (relative, target, current) = resolve_writeback_target(repository, &path, &source)?;
    let (response_commit, response_bytes) = ensure_response_snapshot(
        repository, db, &record, &result, &source, &path, &dispatch_identity, &dispatch_commit, stored_forensic.as_deref(),
    )?;
    let (dirty, matches_dispatch) = target_git_state(repository, &relative, &source_blob)?;
    if dirty || !matches_dispatch {
        return Ok(serde_json::json!({
            "type":"writeback-result",
            "status":"decision-required",
            "result_identity":result,
            "source_identity":source,
            "path":path,
            "master_state":if dirty {"dirty"} else {"clean"},
            "source_state":if matches_dispatch {"matches-dispatch"} else {"changed-since-dispatch"},
            "reason":if dirty {"master-dirty"} else {"changed-since-dispatch"},
            "inflight_commit":response_commit,
            "decision_required":true
        }));
    }

    std::fs::write(&target, &response_bytes)?;
    let saved = std::fs::read(&target)?;
    if saved != response_bytes {
        let _ = std::fs::write(&target, current.as_bytes());
        return Err(format!("writeback verification failed for {path}").into());
    }

    if let Err(error) = response_repository::mark_written(db, &result, "accepted", Some(&path), Some(&response_commit)) {
        let _ = std::fs::write(&target, current.as_bytes());
        return Err(error.into());
    }
    run_asc(&asc_command(), ["export", "update-exports", result.as_str()], &[])?;
    response_repository::complete(db, &result)?;
    let after_dirty = git::inspect(repository, std::slice::from_ref(&relative))?
        .into_iter().next().map(|status| status.dirty).unwrap_or(false);

    Ok(serde_json::json!({
        "type":"writeback-result",
        "status":"written",
        "result_identity":result,
        "source_identity":source,
        "path":path,
        "master_state_before":"clean",
        "master_state_after":if after_dirty {"dirty"} else {"clean"},
        "source_state":"matches-dispatch",
        "inflight_commit":response_commit,
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
    // The inflight ledger is the immutable handoff boundary. Record the exact
    // commit-worktree bytes before conversion, upload, or enqueue can begin.
    let dispatch = input.dispatch_identity.clone().unwrap_or_else(|| format!(
        "run-{}-{}",
        std::process::id(),
        std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|v| v.as_nanos()).unwrap_or(0)
    ));
    let inflight_commit = if let Some((_reference, commit)) = db::inflight_dispatch_ledger(&database, &dispatch)? {
        commit
    } else {
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
        ledger.commit.0
    };
    let outcomes = pandoc::run_parallel(&pandoc_binary, jobs, pandoc_parallelism)?;
    let mut calls = Vec::new();
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
        let mut call = serde_json::json!({"type":"call","identity":identity,"content":content,
            "plan":input.plan,
            "extra":{"filename_hint":relative.file_name().and_then(|name| name.to_str()).unwrap_or(expected_slug),
            "source_path":relative.to_string_lossy().replace('\\',"/"),"metadata":metadata}});
        if let Some(directive) = record
            .get("directive")
            .and_then(serde_json::Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
        {
            call["directive"] = serde_json::Value::String(directive.into());
        }
        calls.push(call);
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
    // Enqueue owns call persistence as well as runtime construction. Once the
    // inline records have been handed to asc, svc does not wait for validation
    // or runtime processing; failure keys surface asynchronous errors.
    run_asc_fire_and_forget(&asc, ["enqueue"], &ndjson(&calls)?)?;
    Ok(DispatchRunOutput {
        ok: true,
        operation: "dispatch.run",
        plan: input.plan,
        records: identities.len(),
        calls: identities,
        dispatch,
        inflight_commit,
    })
}


fn refresh_cli() -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let repository = git::root(&std::env::current_dir()?)?;
    git::ensure_info_exclude(&repository, "/.autoscribe/")?;
    let db = open_configured_database()?;
    let server = fetch_server_snapshot(&asc_command())?;
    let refreshed_at = unix_timestamp();
    let (state, state_commit) = publish_control_state(&repository, &db, &server, &refreshed_at)?;
    Ok(serde_json::json!({
        "ok":true,
        "operation":"refresh",
        "refreshed_at":refreshed_at,
        "dispatches":state["dispatches"],
        "catalogs":state["catalogs"],
        "config":state["config"],
        "state_ref":git::CONFIG_REF,
        "state_path":"state/control.json",
        "state_commit":state_commit
    }))
}

fn autoscribe_state_dir(repository: &Path) -> PathBuf {
    // Private process-control scratch only. Frontends never read this directory;
    // frontend-visible state is committed under state/ on autoscribe/config.
    repository.join(".autoscribe")
}

fn publish_control_state(
    repository: &Path,
    db: &Database,
    server: &serde_json::Value,
    refreshed_at: &str,
) -> Result<(serde_json::Value, String), Box<dyn std::error::Error>> {
    // State is stored in the same Git history as config, but it must describe
    // one coherent plans/instructions payload even if Plan Manager writes a
    // new plan concurrently. Rebuild the state if the payload changes while
    // the state commit is being appended.
    for _ in 0..4 {
        let payload_revision = git::config_head(repository)?;
        let mut catalogs = match payload_revision.as_ref() {
            Some(revision) => catalogs_with_local_config_at(server, repository, &revision.0)?,
            None => catalogs_from_server(server),
        };
        annotate_plan_usage(db, &mut catalogs)?;
        let state = serde_json::json!({
            "version":1,
            "refreshed_at":refreshed_at,
            "catalogs":catalogs,
            "git":git::summary(repository)?,
            "pipeline":db::system_counts(db)?,
            "config":{
                "payload_revision":payload_revision.as_ref().map(|v|v.0.clone()),
                "transport":"git-push"
            },
            "dispatches":[],
        });
        let commit = git::config_upsert_json(
            repository,
            "state",
            "control",
            &state,
            "AUTOSCRIBE CONFIG control state",
        )?;
        let payload_still_matches = match payload_revision.as_ref() {
            Some(revision) => git::config_payload_equal(repository, &revision.0, &commit.0)?,
            None => {
                git::config_list_json_at(repository, "plans", &commit.0)?.is_empty()
                    && git::config_list_json_at(repository, "instructions", &commit.0)?.is_empty()
            }
        };
        if payload_still_matches {
            return Ok((state, commit.0));
        }
    }
    Err("configuration payload kept changing while publishing control state".into())
}

fn plan_usage(db: &Database, slug: &str) -> Result<(f64, u64, Option<String>), Box<dyn std::error::Error>> {
    let score_key = format!("plan.usage.score.{slug}");
    let count_key = format!("plan.usage.count.{slug}");
    let last_key = format!("plan.usage.last.{slug}");
    let stored_score = db::meta_get(db, &score_key)?.and_then(|value| value.parse::<f64>().ok()).unwrap_or(0.0);
    let count = db::meta_get(db, &count_key)?.and_then(|value| value.parse::<u64>().ok()).unwrap_or(0);
    let last = db::meta_get(db, &last_key)?;
    let now = unix_timestamp().parse::<f64>().unwrap_or(0.0);
    let last_seconds = last.as_deref().and_then(|value| value.parse::<f64>().ok()).unwrap_or(now);
    let age_days = ((now - last_seconds).max(0.0)) / 86_400.0;
    let half_life_days = 30.0_f64;
    let score = stored_score * 2.0_f64.powf(-age_days / half_life_days);
    Ok((score, count, last))
}

fn record_plan_use(db: &Database, slug: &str) -> Result<(), Box<dyn std::error::Error>> {
    let (score, count, _) = plan_usage(db, slug)?;
    let now = unix_timestamp();
    let score_key = format!("plan.usage.score.{slug}");
    let count_key = format!("plan.usage.count.{slug}");
    let last_key = format!("plan.usage.last.{slug}");
    db::meta_set_many(db, &[
        (score_key.as_str(), format!("{:.12}", score + 1.0)),
        (count_key.as_str(), (count + 1).to_string()),
        (last_key.as_str(), now),
    ])?;
    Ok(())
}

fn annotate_plan_usage(db: &Database, catalogs: &mut serde_json::Value) -> Result<(), Box<dyn std::error::Error>> {
    let plans = catalogs.get_mut("plans").and_then(serde_json::Value::as_array_mut)
        .ok_or("catalog plans must be an array")?;
    for plan in plans {
        let slug = ["record_identity", "slug", "key"].into_iter()
            .find_map(|field| plan.get(field).and_then(serde_json::Value::as_str))
            .unwrap_or("").trim().to_string();
        if slug.is_empty() { continue; }
        let (score, count, last) = plan_usage(db, &slug)?;
        if let Some(object) = plan.as_object_mut() {
            object.insert("usage_score".into(), serde_json::json!(score));
            object.insert("use_count".into(), serde_json::json!(count));
            if let Some(last) = last { object.insert("last_used_at".into(), serde_json::Value::String(last)); }
        }
    }
    Ok(())
}

fn reconcile_git_dispatch_commits(
    repository: &Path,
    db: &Database,
) -> Result<Vec<serde_json::Value>, Box<dyn std::error::Error>> {
    let branch = git::current_branch(repository)?;
    let head = git::head(repository)?.0;
    let cursor_key = format!("git.dispatch.cursor.{branch}");
    let cursor = db::meta_get(db, &cursor_key)?;
    let commits = match cursor.as_deref() {
        None => vec![head.clone()],
        Some(previous) if previous == head => Vec::new(),
        Some(previous) => {
            if !git_is_ancestor(repository, previous, &head)? {
                db::meta_set_many(db, &[(cursor_key.as_str(), head.clone())])?;
                return Ok(vec![serde_json::json!({
                    "status":"cursor-reset",
                    "branch":branch,
                    "reason":"history-rewritten",
                    "head":head
                })]);
            }
            git_lines(repository, &["rev-list", "--reverse", &format!("{previous}..{head}")])?
        }
    };

    let mut output = Vec::new();
    for commit in commits {
        let message = git_text(repository, &["show", "-s", "--format=%B", &commit])?;
        let trailers = dispatch_trailers(&message)?;
        if let Some(plan) = trailers.plan {
            let receipt_key = format!("git.dispatch.receipt.{commit}.{plan}");
            if db::meta_get(db, &receipt_key)?.is_some() {
                output.push(serde_json::json!({"status":"already-dispatched","commit":commit,"plan":plan}));
            } else {
                let result = dispatch_commit_worktree(repository, &commit, &plan, &trailers.documents)?;
                record_plan_use(db, &plan)?;
                db::meta_set_many(db, &[(receipt_key.as_str(), unix_timestamp())])?;
                output.push(serde_json::json!({
                    "status":"dispatched",
                    "commit":commit,
                    "plan":plan,
                    "dispatch":result.get("dispatch").cloned().unwrap_or(serde_json::Value::Null),
                    "records":result.get("records").cloned().unwrap_or(serde_json::Value::Null)
                }));
            }
        } else {
            output.push(serde_json::json!({"status":"ignored","commit":commit}));
        }
        db::meta_set_many(db, &[(cursor_key.as_str(), commit.clone())])?;
    }
    Ok(output)
}

struct DispatchTrailers {
    plan: Option<String>,
    documents: Vec<String>,
}

fn dispatch_trailers(message: &str) -> Result<DispatchTrailers, Box<dyn std::error::Error>> {
    let mut plans = Vec::new();
    let mut documents = Vec::new();
    let lines = message.lines().collect::<Vec<_>>();
    let end = lines.iter().rposition(|line| !line.trim().is_empty())
        .map(|index| index + 1).unwrap_or(0);
    let start = lines[..end].iter().rposition(|line| line.trim().is_empty())
        .map(|index| index + 1).unwrap_or(0);
    for line in &lines[start..end] {
        if let Some(value) = line.strip_prefix("Autoscribe-Plan:") {
            let value = value.trim();
            if value.is_empty() { return Err("Autoscribe-Plan trailer is blank".into()); }
            plans.push(value.to_string());
        }
        if let Some(value) = line.strip_prefix("Autoscribe-Document:") {
            let value = value.trim();
            if value.is_empty() { return Err("Autoscribe-Document trailer is blank".into()); }
            if !value.chars().all(|character| character.is_ascii_alphanumeric() || matches!(character, '.' | '-' | '_')) {
                return Err(format!("Autoscribe-Document must contain a document slug: {value}").into());
            }
            if documents.iter().any(|document| document == value) {
                return Err(format!("duplicate Autoscribe-Document trailer: {value}").into());
            }
            documents.push(value.to_string());
        }
    }
    plans.sort();
    plans.dedup();
    let plan = match plans.len() {
        0 => None,
        1 => plans.into_iter().next(),
        _ => return Err("a commit may contain only one distinct Autoscribe-Plan trailer".into()),
    };
    if plan.is_none() && !documents.is_empty() {
        return Err("Autoscribe-Document trailer requires Autoscribe-Plan".into());
    }
    if plan.is_some() && documents.is_empty() {
        return Err("Autoscribe-Plan trailer requires at least one Autoscribe-Document trailer".into());
    }
    Ok(DispatchTrailers { plan, documents })
}

fn dispatch_commit_worktree(
    repository: &Path,
    commit: &str,
    plan: &str,
    document_slugs: &[String],
) -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let temporary = std::env::temp_dir().join(format!(
        "autoscribe-dispatch-{}-{}-{}",
        std::process::id(),
        &commit[..commit.len().min(12)],
        std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)?.as_nanos()
    ));
    std::fs::create_dir_all(&temporary)?;
    let worktree = temporary.join("worktree");
    let add = Command::new("/usr/bin/git")
        .arg("-C").arg(repository)
        .args(["worktree", "add", "--quiet", "--detach"])
        .arg(&worktree).arg(commit).output()?;
    if !add.status.success() {
        let _ = std::fs::remove_dir_all(&temporary);
        return Err(format!("could not create dispatch worktree: {}", String::from_utf8_lossy(&add.stderr).trim()).into());
    }
    let result = (|| {
        for slug in document_slugs {
            if !is_dispatch_target_slug(slug) {
                return Err(format!("Autoscribe-Document is not a dispatch target: {slug}").into());
            }
        }
        let dispatch_identity = format!("git-{}-{}", &commit[..commit.len().min(16)], safe_dispatch_part(plan));
        // Slug resolution now happens inside the detached exact-commit
        // worktree. The filepath is derived state, never part of the commit
        // message contract.
        run_internal_dispatch(&worktree, plan, document_slugs, &dispatch_identity)
    })();
    let remove = Command::new("/usr/bin/git")
        .arg("-C").arg(repository)
        .args(["worktree", "remove", "--force"])
        .arg(&worktree).output();
    let _ = std::fs::remove_dir_all(&temporary);
    if let Ok(remove) = remove {
        if !remove.status.success() && result.is_ok() {
            return Err(format!("dispatch succeeded but temporary worktree cleanup failed: {}", String::from_utf8_lossy(&remove.stderr).trim()).into());
        }
    }
    result
}

fn is_dispatch_target_slug(slug: &str) -> bool {
    let prefix = slug.split('.').next().unwrap_or("").to_ascii_lowercase();
    !matches!(prefix.as_str(), "plan" | "ins" | "std" | "rul" | "rol" | "ctx" | "tsk" | "spc" | "ref")
}

fn safe_dispatch_part(value: &str) -> String {
    let mut out = value.chars().map(|ch| if ch.is_ascii_alphanumeric() { ch } else { '-' }).collect::<String>();
    while out.contains("--") { out = out.replace("--", "-"); }
    out.trim_matches('-').chars().take(48).collect()
}

fn run_internal_dispatch(
    worktree: &Path,
    plan: &str,
    documents: &[String],
    dispatch_identity: &str,
) -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let executable = std::env::current_exe()?;
    let mut child = Command::new(executable)
        .arg("__dispatch-run")
        .current_dir(worktree)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;
    let input = serde_json::to_vec(&serde_json::json!({
        "version":1,
        "plan":plan,
        "documents":documents,
        "dispatch_identity":dispatch_identity
    }))?;
    if let Some(mut stdin) = child.stdin.take() {
        use std::io::Write;
        stdin.write_all(&input)?;
    }
    let output = child.wait_with_output()?;
    let text = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if !output.status.success() {
        let error = if output.stderr.is_empty() { text } else { String::from_utf8_lossy(&output.stderr).trim().to_string() };
        return Err(format!("Git-triggered dispatch failed: {error}").into());
    }
    let value: serde_json::Value = serde_json::from_str(&text)?;
    if value.get("ok").and_then(serde_json::Value::as_bool) != Some(true) {
        return Err(value.get("error").and_then(serde_json::Value::as_str).unwrap_or("dispatch failed").to_string().into());
    }
    Ok(value)
}

fn git_text(repository: &Path, args: &[&str]) -> Result<String, Box<dyn std::error::Error>> {
    let output = Command::new("/usr/bin/git").arg("-C").arg(repository).args(args).output()?;
    if !output.status.success() {
        return Err(format!("git {} failed: {}", args.join(" "), String::from_utf8_lossy(&output.stderr).trim()).into());
    }
    Ok(String::from_utf8(output.stdout)?)
}

fn git_lines(repository: &Path, args: &[&str]) -> Result<Vec<String>, Box<dyn std::error::Error>> {
    Ok(git_text(repository, args)?.lines().map(str::trim).filter(|line| !line.is_empty()).map(str::to_string).collect())
}

fn git_is_ancestor(repository: &Path, ancestor: &str, descendant: &str) -> Result<bool, Box<dyn std::error::Error>> {
    let output = Command::new("/usr/bin/git").arg("-C").arg(repository)
        .args(["merge-base", "--is-ancestor", ancestor, descendant]).output()?;
    match output.status.code() {
        Some(0) => Ok(true),
        Some(1) => Ok(false),
        _ => Err(format!("could not compare Git dispatch cursor: {}", String::from_utf8_lossy(&output.stderr).trim()).into()),
    }
}

fn configured_pandoc_binary() -> Result<PathBuf, Box<dyn std::error::Error>> {
    let path = env::var_os("PANDOC_BIN").map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/usr/bin/pandoc"));
    if !path.is_absolute() { return Err("PANDOC_BIN must be absolute".into()); }
    Ok(path)
}

fn configured_pandoc_filter() -> Result<PathBuf, Box<dyn std::error::Error>> {
    let path = if let Some(path) = env::var_os("AUTOSCRIBE_PANDOC_FILTER") {
        PathBuf::from(path)
    } else {
        let root = env::var_os("AUTOSCRIBE_ROOT").map(PathBuf::from).unwrap_or_else(|| {
            PathBuf::from(env::var_os("HOME").unwrap_or_else(|| "/home/jeremy".into())).join("Work/Loom")
        });
        root.join("platform/pandoc/filters/emit/emit_ndjson.lua")
    };
    if !path.is_absolute() { return Err("AUTOSCRIBE_PANDOC_FILTER must be absolute".into()); }
    if !path.is_file() { return Err(format!("Pandoc filter not found: {}", path.display()).into()); }
    Ok(path)
}

fn configured_pandoc_parallelism() -> usize {
    env::var("AUTOSCRIBE_PANDOC_PARALLELISM").ok()
        .and_then(|value| value.parse().ok()).filter(|value| *value >= 2)
        .unwrap_or_else(|| std::thread::available_parallelism().map(usize::from).unwrap_or(2).max(2))
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
    let mut ordered = Vec::new();
    for slug in requested {
        let slug = slug.trim();
        if slug.is_empty() { return Err("document slug cannot be blank".into()); }
        if !wanted.insert(slug.to_string()) { return Err(format!("duplicate document slug: {slug}").into()); }
        ordered.push(slug.to_string());
    }
    let matches = instruction_sync::resolve_slug_paths(repository, &wanted)?;
    let mut resolved = Vec::new();
    for slug in ordered {
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

fn define_plan_snapshot() -> ExitCode {
    // Compatibility/read-only command. Frontends should read the same record
    // directly from refs/heads/autoscribe/config rather than invoking svc.
    command_output("define-plan.snapshot", snapshot_from_config_ref())
}

fn snapshot_from_config_ref() -> Result<DefinePlanSnapshotOutput, Box<dyn std::error::Error>> {
    let repository = git::root(&std::env::current_dir()?)?;
    let state = git::config_get_json(&repository, "state", "control")?
        .ok_or("configuration state has not been published yet; run refresh")?;
    let catalogs = state.get("catalogs").cloned()
        .ok_or("published configuration state has no catalogs")?;
    let refreshed_at = state.get("refreshed_at").and_then(serde_json::Value::as_str).map(str::to_string);
    Ok(DefinePlanSnapshotOutput {
        ok: true,
        operation: "define-plan.snapshot",
        catalogs,
        refreshed_at,
    })
}

fn open_configured_database() -> Result<Database, Box<dyn std::error::Error>> {
    let database_path = configured_database_path()?;
    if let Some(parent) = database_path.parent() { std::fs::create_dir_all(parent)?; }
    let db = Database::open_path(&database_path)?;
    db::migrate(&db)?;
    Ok(db)
}


fn fetch_server_snapshot(asc: &Path) -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let control: serde_json::Value =
        serde_json::from_slice(&run_asc_capture(asc, ["control", "snapshot"], &[])?)?;
    if !control.is_object() {
        return Err("control snapshot must be an object".into());
    }
    Ok(control)
}

fn catalogs_with_local_config_at(
    server: &serde_json::Value,
    repository: &Path,
    revision: &str,
) -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let mut catalogs = catalogs_from_server(server);

    let instructions = catalogs.get_mut("instructions")
        .and_then(serde_json::Value::as_array_mut)
        .ok_or("catalog instructions must be an array")?;
    let mut instruction_by_slug = std::collections::BTreeMap::<String, serde_json::Value>::new();
    for record in instructions.drain(..) {
        let slug = instruction_record_slug(&record);
        if !slug.is_empty() { instruction_by_slug.insert(slug, record); }
    }
    for record in git::config_list_json_at(repository, "instructions", revision)? {
        let slug = instruction_record_slug(&record);
        if slug.is_empty() { continue; }
        let extra = record.get("extra").and_then(serde_json::Value::as_object);
        instruction_by_slug.insert(slug.clone(), serde_json::json!({
            "slug": slug,
            "record_identity": record.get("identity").and_then(serde_json::Value::as_str).unwrap_or(""),
            "title": extra.and_then(|v| v.get("title")).cloned().unwrap_or_else(|| serde_json::Value::String(slug.clone())),
            "scope": extra.and_then(|v| v.get("scope")).cloned().unwrap_or_else(|| serde_json::Value::String("local".into())),
            "component": extra.and_then(|v| v.get("component")).cloned().unwrap_or_else(|| serde_json::Value::String(instruction_component_from_slug(&slug))),
            "path": extra.and_then(|v| v.get("source_path")).cloned().unwrap_or(serde_json::Value::Null),
            "source":"autoscribe/config"
        }));
    }
    instructions.extend(instruction_by_slug.into_values());

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
    for plan in plan_repository::list_at(repository, revision)? {
        let slug = ["record_identity", "slug"].into_iter()
            .find_map(|field| plan.get(field).and_then(serde_json::Value::as_str))
            .unwrap_or("").to_string();
        if !slug.is_empty() { by_slug.insert(slug, plan); }
    }
    plans.extend(by_slug.into_values());
    Ok(catalogs)
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
    let list = |name: &str| registry_records(registries.and_then(|all| all.get(name)), name);
    serde_json::json!({
        "instructions": list("instructions"),
        "plans": list("plans"),
        "engines": list("engines"),
        "models": list("models"),
        "scripts": list("local_scripts"),
        "rag_profiles": list("rag_profiles"),
    })
}

fn registry_records(value: Option<&serde_json::Value>, kind: &str) -> Vec<serde_json::Value> {
    let mut records = Vec::new();
    match value {
        Some(serde_json::Value::Object(map)) => for (key, value) in map {
            let mut record = value.as_object().cloned().unwrap_or_default();
            record.entry("key").or_insert_with(|| serde_json::Value::String(key.clone()));
            normalize_catalog_record(&mut record, kind, key);
            records.push(serde_json::Value::Object(record));
        },
        Some(serde_json::Value::Array(values)) => for value in values {
            let mut record = value.as_object().cloned().unwrap_or_default();
            let key = ["slug", "record_identity", "key"].into_iter().find_map(|field| record.get(field).and_then(serde_json::Value::as_str)).unwrap_or("").to_string();
            normalize_catalog_record(&mut record, kind, &key);
            records.push(serde_json::Value::Object(record));
        },
        _ => {}
    }
    records
}

fn normalize_catalog_record(record: &mut serde_json::Map<String, serde_json::Value>, kind: &str, fallback: &str) {
    match kind {
        "instructions" => normalize_instruction_record(record, fallback),
        "plans" => normalize_plan_catalog_record(record, fallback),
        _ => {}
    }
}

fn normalize_plan_catalog_record(record: &mut serde_json::Map<String, serde_json::Value>, fallback: &str) {
    let slug = ["record_identity", "slug", "key"].into_iter()
        .find_map(|field| record.get(field).and_then(serde_json::Value::as_str))
        .filter(|value| !value.trim().is_empty())
        .unwrap_or(fallback).to_string();
    if !slug.is_empty() {
        record.insert("record_identity".into(), serde_json::Value::String(slug));
    }
    if !record.contains_key("payload") {
        if let Some(payload) = record.get("content").filter(|value| value.is_object()).cloned() {
            record.insert("payload".into(), payload);
        }
    }
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
    env::var_os("ASC_BIN").map(PathBuf::from).unwrap_or_else(|| {
        PathBuf::from(env::var_os("HOME").unwrap_or_else(|| "/home/jeremy".into())).join("Python3.13Env/bin/asc")
    })
}

fn run_asc_fire_and_forget<I, S>(asc: &Path, args: I, input: &[u8]) -> Result<(), AscFailure>
where
    I: IntoIterator<Item = S>,
    S: AsRef<std::ffi::OsStr>,
{
    let mut child = Command::new(asc)
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
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
    // Deliberately do not wait. asc is responsible for recording any enqueue
    // failure after accepting the payload.
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

#[cfg(test)]
mod watch_dispatch_tests {
    use super::*;

    #[test]
    fn parses_repeated_document_trailers_in_order() {
        let trailers = dispatch_trailers(
            "Editorial commit\n\nAutoscribe-Plan: plan.test\nAutoscribe-Document: cnt.one\nAutoscribe-Document: psg.two\n"
        ).unwrap();
        assert_eq!(trailers.plan.as_deref(), Some("plan.test"));
        assert_eq!(trailers.documents, vec!["cnt.one", "psg.two"]);
    }

    #[test]
    fn ignores_trailer_examples_outside_the_final_trailer_block() {
        let trailers = dispatch_trailers(
            "Explain Autoscribe trailers\n\nAutoscribe-Plan: example.only\n\nNo dispatch in this commit.\n"
        ).unwrap();
        assert!(trailers.plan.is_none());
        assert!(trailers.documents.is_empty());
    }

    #[test]
    fn rejects_a_filepath_instead_of_a_slug() {
        let error = dispatch_trailers(
            "Editorial commit\n\nAutoscribe-Plan: plan.test\nAutoscribe-Document: Content/Outside.md\n"
        ).err().unwrap().to_string();
        assert!(error.contains("document slug"));
    }

    #[test]
    fn document_resolution_preserves_trailer_order() {
        let nonce = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)
            .unwrap().as_nanos();
        let root = std::env::temp_dir().join(format!("autoscribe-document-order-{nonce}"));
        std::fs::create_dir(&root).unwrap();
        std::fs::write(root.join("First.md"), "---\nslug: cnt.first\n---\nFirst\n").unwrap();
        std::fs::write(root.join("Second.md"), "---\nslug: psg.second\n---\nSecond\n").unwrap();
        let resolved = resolve_document_slugs(
            &root,
            &["psg.second".to_string(), "cnt.first".to_string()],
        ).unwrap();
        assert_eq!(resolved.iter().map(|(slug, _)| slug.as_str()).collect::<Vec<_>>(),
            vec!["psg.second", "cnt.first"]);
        std::fs::remove_dir_all(root).unwrap();
    }
}
