use crate::{ServiceError, ServiceResult, types::*};
use std::{
    ffi::OsStr,
    fs,
    path::{Component, Path, PathBuf},
    process::{Command, Output},
    io::Write,
    time::{SystemTime, UNIX_EPOCH},
};
use serde::{Deserialize, Serialize};
use serde_json::json;

const GIT: &str = "/usr/bin/git";
const INFLIGHT_REF: &str = "refs/heads/autoscribe/inflight";
pub const CONFIG_REF: &str = "refs/heads/autoscribe/config";
pub const CONFIG_SYNCED_REF: &str = "refs/autoscribe/config-synced";
pub const CONFIG_INSTRUCTIONS_SUBMITTED_REF: &str = "refs/autoscribe/config-instructions-submitted";
pub const CONFIG_PLANS_SUBMITTED_REF: &str = "refs/autoscribe/config-plans-submitted";
pub const CONFIG_SOURCE_REF: &str = "refs/autoscribe/config-source";

pub fn root(path: &Path) -> ServiceResult<PathBuf> {
    repository_root(path)
}

pub fn head(repo: &Path) -> ServiceResult<CommitId> {
    let repo = repository_root(repo)?;
    Ok(CommitId(revision(&repo, "HEAD")?))
}

pub fn current_branch(repo: &Path) -> ServiceResult<String> {
    let repo = repository_root(repo)?;
    let branch = text(&git(&repo, ["branch", "--show-current"])?)
        .trim()
        .to_string();
    if branch.is_empty() {
        return Err(ServiceError::Conflict(
            "dispatch preparation requires an attached source branch".into(),
        ));
    }
    Ok(branch)
}

/// Ensure a repository-local ignore rule is present in `.git/info/exclude`.
/// This changes neither the working tree nor any committed `.gitignore` file.
pub fn ensure_info_exclude(repo: &Path, pattern: &str) -> ServiceResult<()> {
    let repo = repository_root(repo)?;
    let pattern = one_line("Git exclude pattern", pattern)?;
    let output = git(&repo, ["rev-parse", "--git-path", "info/exclude"])?;
    let raw = text(&output).trim().to_string();
    if raw.is_empty() {
        return Err(ServiceError::Io("Git did not return an info/exclude path".into()));
    }
    let mut exclude = PathBuf::from(raw);
    if !exclude.is_absolute() {
        exclude = repo.join(exclude);
    }
    if let Some(parent) = exclude.parent() {
        fs::create_dir_all(parent).map_err(io)?;
    }
    let existing = match fs::read_to_string(&exclude) {
        Ok(value) => value,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => String::new(),
        Err(error) => return Err(io(error)),
    };
    if existing.lines().any(|line| line.trim() == pattern) {
        return Ok(());
    }
    let mut file = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&exclude)
        .map_err(io)?;
    if !existing.is_empty() && !existing.ends_with('\n') {
        file.write_all(b"\n").map_err(io)?;
    }
    file.write_all(pattern.as_bytes()).map_err(io)?;
    file.write_all(b"\n").map_err(io)?;
    Ok(())
}

pub fn summary(repo: &Path) -> ServiceResult<serde_json::Value> {
    let repo = repository_root(repo)?;
    let branch = text(&git(&repo, ["branch", "--show-current"])?).trim().to_string();
    let branch_label = if branch.is_empty() {
        "detached HEAD".to_string()
    } else {
        branch
    };
    let porcelain = text(&git(&repo, ["status", "--porcelain=v1"])?);
    let mut staged = 0;
    let mut modified = 0;
    let mut untracked = 0;
    let mut conflicted = 0;
    for line in porcelain.lines().filter(|line| line.len() >= 2) {
        let code = &line[..2];
        if code == "??" { untracked += 1; continue; }
        if code.as_bytes()[0] != b' ' { staged += 1; }
        if code.as_bytes()[1] != b' ' { modified += 1; }
        if matches!(code, "DD" | "AU" | "UD" | "UA" | "DU" | "AA" | "UU") { conflicted += 1; }
    }
    let latest_output = git_status_output(&repo, ["log", "-1", "--format=%h%x09%cr%x09%s"])?;
    let latest = if latest_output.status.success() {
        text(&latest_output).trim().to_string()
    } else {
        String::new()
    };
    let upstream = git_status_output(&repo, ["rev-list", "--left-right", "--count", "@{upstream}...HEAD"])?;
    let (behind, ahead) = if upstream.status.success() {
        let values = text(&upstream).split_whitespace().filter_map(|value| value.parse::<u64>().ok()).collect::<Vec<_>>();
        (values.first().copied(), values.get(1).copied())
    } else { (None, None) };
    Ok(json!({"root":repo,"branch":branch_label,
        "latest":latest,"ahead":ahead,"behind":behind,"staged":staged,"modified":modified,
        "untracked":untracked,"conflicted":conflicted}))
}

pub fn inspect(repo: &Path, paths: &[PathBuf]) -> ServiceResult<Vec<FileStatus>> {
    let repo = repository_root(repo)?;
    paths
        .iter()
        .map(|path| {
            let path = safe_relative_path(path)?;
            let tracked = git(&repo, ["ls-files", "--error-unmatch", "--", path.as_str()]).is_ok();
            let status = git(&repo, ["status", "--porcelain=v1", "--", path.as_str()])?;
            Ok(FileStatus {
                path: PathBuf::from(path),
                tracked,
                dirty: !text(&status).trim().is_empty(),
            })
        })
        .collect()
}

pub fn commit(repo: &Path, request: CommitRequest) -> ServiceResult<CommitId> {
    let repo = repository_root(repo)?;
    let allow_empty = request.purpose == CommitPurpose::DispatchWriteback;
    if request.paths.is_empty() {
        return Err(ServiceError::InvalidInput(
            "commit requires at least one path".into(),
        ));
    }
    let message = one_line("commit message", &request.message)?;
    let paths = request
        .paths
        .iter()
        .map(|path| safe_relative_path(path))
        .collect::<ServiceResult<Vec<_>>>()?;

    let mut add = vec!["add".to_string(), "--".into()];
    add.extend(paths.iter().cloned());
    git(&repo, add)?;

    let mut changed = vec![
        "diff".to_string(),
        "--cached".into(),
        "--quiet".into(),
        "--".into(),
    ];
    changed.extend(paths.iter().cloned());
    let status = git_status(&repo, changed)?;
    if status.success() && !allow_empty {
        return Err(ServiceError::Conflict(
            "selected paths have no changes to commit".into(),
        ));
    }
    if !status.success() && status.code() != Some(1) {
        return Err(ServiceError::Io(
            "could not inspect staged Git changes".into(),
        ));
    }

    let purpose = format!("AutoScribe-Purpose: {}", purpose_name(&request.purpose));
    let mut args = vec![
        "commit".to_string(),
        "--only".into(),
        "-m".into(),
        message,
        "-m".into(),
        purpose,
        "--".into(),
    ];
    if allow_empty {
        args.insert(2, "--allow-empty".into());
    }
    args.extend(paths);
    git(&repo, args)?;
    Ok(CommitId(revision(&repo, "HEAD")?))
}

/// Append an immutable source snapshot to the AutoScribe ledger without
/// changing HEAD, the user's index, or the working tree.
pub fn append_inflight_snapshot(
    repo: &Path,
    request: &LedgerSnapshotRequest,
) -> ServiceResult<LedgerSnapshot> {
    let repo = repository_root(repo)?;
    let dispatch = ref_component("dispatch identity", &request.dispatch.0)?;
    let plan = one_line("plan identity", &request.plan.0)?;
    if request.sources.is_empty() {
        return Err(ServiceError::InvalidInput("ledger snapshot requires source files".into()));
    }

    for _ in 0..4 {
        let old = optional_revision(&repo, INFLIGHT_REF)?;
        let base = old.clone().unwrap_or(revision(&repo, "HEAD")?);
        let temporary_index = temporary_index_path();
        let result = (|| {
            git_with_env(&repo, ["read-tree", base.as_str()], &temporary_index)?;
            let mut blobs = Vec::new();
            for source in &request.sources {
                let path = safe_relative_path(&source.path)?;
                let blob = hash_bytes(&repo, &source.bytes)?;
                git_with_env(
                    &repo,
                    ["update-index", "--add", "--cacheinfo", "100644", blob.as_str(), path.as_str()],
                    &temporary_index,
                )?;
                blobs.push((PathBuf::from(path), blob));
            }
            let tree = text(&git_with_env(&repo, ["write-tree"], &temporary_index)?)
                .trim().to_string();
            let mut message = format!(
                "AUTOSCRIBE INFLIGHT {dispatch}\n\nDispatch: {dispatch}\nPlan: {plan}"
            );
            for source in &request.sources {
                message.push_str(&format!(
                    "\nRecord: {}\t{}",
                    one_line("record slug", &source.slug)?,
                    safe_relative_path(&source.path)?
                ));
            }
            let commit = commit_tree(&repo, &tree, old.as_deref(), &message)?;
            let expected = old.as_deref().unwrap_or("0000000000000000000000000000000000000000");
            let update = git_status_output(
                &repo,
                ["update-ref", "-m", "AutoScribe inflight ledger", INFLIGHT_REF, commit.as_str(), expected],
            )?;
            if !update.status.success() {
                return Err(ServiceError::Conflict("inflight ledger advanced concurrently".into()));
            }
            Ok(LedgerSnapshot {
                reference: INFLIGHT_REF.into(),
                commit: CommitId(commit),
                blobs,
            })
        })();
        let _ = fs::remove_file(&temporary_index);
        match result {
            Err(ServiceError::Conflict(message)) if message.contains("advanced concurrently") => continue,
            other => return other,
        }
    }
    Err(ServiceError::Conflict("inflight ledger remained busy after retries".into()))
}

pub fn append_response_snapshot(
    repo: &Path,
    dispatch: &str,
    result: &str,
    source: &str,
    outcome: &str,
    source_path: &Path,
    bytes: &[u8],
) -> ServiceResult<CommitId> {
    let repo = repository_root(repo)?;
    let dispatch = one_line("dispatch identity", dispatch)?;
    let result = one_line("result identity", result)?;
    let source = one_line("source identity", source)?;
    let source_path = safe_relative_path(source_path)?;
    if !matches!(outcome, "saved" | "accepted" | "declined") {
        return Err(ServiceError::InvalidInput("response outcome must be saved, accepted, or declined".into()));
    }
    for _ in 0..4 {
        let old = optional_revision(&repo, INFLIGHT_REF)?.ok_or_else(|| {
            ServiceError::Conflict("inflight ledger does not exist".into())
        })?;
        let temporary_index = temporary_index_path();
        let attempt = (|| {
            git_with_env(&repo, ["read-tree", old.as_str()], &temporary_index)?;
            let blob = hash_bytes(&repo, bytes)?;
            git_with_env(
                &repo,
                [
                    "update-index",
                    "--add",
                    "--cacheinfo",
                    "100644",
                    blob.as_str(),
                    source_path.as_str(),
                ],
                &temporary_index,
            )?;
            let tree = text(&git_with_env(&repo, ["write-tree"], &temporary_index)?)
                .trim()
                .to_string();
            let message = format!(
                "AUTOSCRIBE RESPONSE {outcome}\n\nDispatch: {dispatch}\nResult: {result}\nSource: {source}\nSource-Path: {source_path}\nOutcome: {outcome}"
            );
            let commit = commit_tree(&repo, &tree, Some(&old), &message)?;
            let update = git_status_output(
                &repo,
                [
                    "update-ref",
                    "-m",
                    "AutoScribe response snapshot",
                    INFLIGHT_REF,
                    commit.as_str(),
                    old.as_str(),
                ],
            )?;
            if !update.status.success() {
                return Err(ServiceError::Conflict("inflight ledger advanced concurrently".into()));
            }
            Ok(CommitId(commit))
        })();
        let _ = fs::remove_file(&temporary_index);
        match attempt {
            Err(ServiceError::Conflict(message)) if message.contains("advanced concurrently") => continue,
            other => return other,
        }
    }
    Err(ServiceError::Conflict("inflight ledger remained busy after retries".into()))
}

pub fn append_response_event(
    repo: &Path,
    dispatch: &str,
    result: &str,
    source: &str,
    outcome: &str,
    writeback: Option<&str>,
) -> ServiceResult<CommitId> {
    let repo = repository_root(repo)?;
    let dispatch = one_line("dispatch identity", dispatch)?;
    let result = one_line("result identity", result)?;
    let source = one_line("source identity", source)?;
    if !matches!(outcome, "accepted" | "declined") {
        return Err(ServiceError::InvalidInput("response outcome must be accepted or declined".into()));
    }
    for _ in 0..4 {
        let old = optional_revision(&repo, INFLIGHT_REF)?.ok_or_else(|| {
            ServiceError::Conflict("inflight ledger does not exist".into())
        })?;
        let tree = text(&git(&repo, ["show", "-s", "--format=%T", old.as_str()])?)
            .trim().to_string();
        let mut message = format!(
            "AUTOSCRIBE RESPONSE {outcome}\n\nDispatch: {dispatch}\nResult: {result}\nSource: {source}\nOutcome: {outcome}"
        );
        if let Some(writeback) = writeback {
            message.push_str(&format!("\nWriteback-Commit: {}", one_line("writeback commit", writeback)?));
        }
        let commit = commit_tree(&repo, &tree, Some(&old), &message)?;
        let update = git_status_output(&repo, [
            "update-ref", "-m", "AutoScribe response event", INFLIGHT_REF,
            commit.as_str(), old.as_str(),
        ])?;
        if update.status.success() { return Ok(CommitId(commit)); }
    }
    Err(ServiceError::Conflict("inflight ledger remained busy after retries".into()))
}

pub fn append_dispatch_terminal_event(repo: &Path, dispatch: &str, outcome: &str, reason: Option<&str>) -> ServiceResult<CommitId> {
    let repo = repository_root(repo)?;
    let dispatch = one_line("dispatch identity", dispatch)?;
    if !matches!(outcome, "completed" | "failed" | "cancelled") {
        return Err(ServiceError::InvalidInput("terminal outcome must be completed, failed, or cancelled".into()));
    }
    for _ in 0..4 {
        let old = optional_revision(&repo, INFLIGHT_REF)?.ok_or_else(|| ServiceError::Conflict("inflight ledger does not exist".into()))?;
        let tree = text(&git(&repo, ["show", "-s", "--format=%T", old.as_str()])?).trim().to_string();
        let mut message = format!("AUTOSCRIBE DISPATCH {outcome}\n\nDispatch: {dispatch}\nOutcome: {outcome}");
        if let Some(reason) = reason { message.push_str(&format!("\nReason: {}", one_line("terminal reason", reason)?)); }
        let commit = commit_tree(&repo, &tree, Some(&old), &message)?;
        let update = git_status_output(&repo, ["update-ref", "-m", "AutoScribe terminal dispatch", INFLIGHT_REF, commit.as_str(), old.as_str()])?;
        if update.status.success() { return Ok(CommitId(commit)); }
    }
    Err(ServiceError::Conflict("inflight ledger remained busy after retries".into()))
}



/// Read the current AutoScribe configuration ledger head. The configuration
/// ledger is an orphan history: it shares the repository object database but
/// is never checked out into the user's working tree.
pub fn config_head(repo: &Path) -> ServiceResult<Option<CommitId>> {
    let repo = repository_root(repo)?;
    Ok(optional_revision(&repo, CONFIG_REF)?.map(CommitId))
}

pub fn config_source_head(repo: &Path) -> ServiceResult<Option<CommitId>> {
    let repo = repository_root(repo)?;
    Ok(optional_revision(&repo, CONFIG_SOURCE_REF)?.map(CommitId))
}

pub fn mark_config_source(repo: &Path, commit: &str) -> ServiceResult<()> {
    let repo = repository_root(repo)?;
    let commit = revision(&repo, commit)?;
    git(&repo, ["update-ref", "-m", "AutoScribe config source", CONFIG_SOURCE_REF, commit.as_str()])?;
    Ok(())
}

pub fn config_synced_head(repo: &Path) -> ServiceResult<Option<CommitId>> {
    let repo = repository_root(repo)?;
    Ok(optional_revision(&repo, CONFIG_SYNCED_REF)?.map(CommitId))
}

pub fn config_category_submitted_head(repo: &Path, category: &str) -> ServiceResult<Option<CommitId>> {
    let repo = repository_root(repo)?;
    let reference = config_submitted_ref(category)?;
    Ok(optional_revision(&repo, reference)?.map(CommitId))
}

pub fn config_category_revision_is_submitted(repo: &Path, category: &str, revision_spec: &str) -> ServiceResult<bool> {
    let repo = repository_root(repo)?;
    let category = config_category(category)?;
    let revision = revision(&repo, revision_spec)?;
    let reference = config_submitted_ref(&category)?;
    let submitted = optional_revision(&repo, reference)?;
    Ok(config_category_listing(&repo, &category, Some(revision.as_str()))?
        == config_category_listing(&repo, &category, submitted.as_deref())?)
}

pub fn mark_config_category_submitted(repo: &Path, category: &str, commit: &str) -> ServiceResult<()> {
    let repo = repository_root(repo)?;
    let category = config_category(category)?;
    let reference = config_submitted_ref(&category)?;
    let commit = revision(&repo, commit)?;
    git(&repo, ["update-ref", "-m", "AutoScribe config submitted", reference, commit.as_str()])?;
    Ok(())
}

pub fn config_is_synced(repo: &Path) -> ServiceResult<bool> {
    let repo = repository_root(repo)?;
    let head = optional_revision(&repo, CONFIG_REF)?;
    let synced = optional_revision(&repo, CONFIG_SYNCED_REF)?;
    let head_payload = config_payload_listing(&repo, head.as_deref())?;
    let synced_payload = config_payload_listing(&repo, synced.as_deref())?;
    Ok(head_payload == synced_payload)
}

pub fn config_revision_is_synced(repo: &Path, revision_spec: &str) -> ServiceResult<bool> {
    let repo = repository_root(repo)?;
    let revision = revision(&repo, revision_spec)?;
    let synced = optional_revision(&repo, CONFIG_SYNCED_REF)?;
    let revision_payload = config_payload_listing(&repo, Some(revision.as_str()))?;
    let synced_payload = config_payload_listing(&repo, synced.as_deref())?;
    Ok(revision_payload == synced_payload)
}

pub fn config_payload_equal(repo: &Path, left: &str, right: &str) -> ServiceResult<bool> {
    let repo = repository_root(repo)?;
    let left = revision(&repo, left)?;
    let right = revision(&repo, right)?;
    Ok(
        config_payload_listing(&repo, Some(left.as_str()))?
            == config_payload_listing(&repo, Some(right.as_str()))?
    )
}

/// Read one JSON record from the configuration ledger. State records live in
/// the same orphan history as plans/instructions but are not part of the
/// payload synchronized to the remote pipeline.
pub fn config_get_json(
    repo: &Path,
    category: &str,
    identity: &str,
) -> ServiceResult<Option<serde_json::Value>> {
    let repo = repository_root(repo)?;
    let category = config_category(category)?;
    let identity = ref_component("config identity", identity)?;
    let Some(head) = optional_revision(&repo, CONFIG_REF)? else { return Ok(None); };
    let path = format!("{category}/{identity}.json");
    let spec = format!("{head}:{path}");
    let output = git_status_output(&repo, ["show", spec.as_str()])?;
    if !output.status.success() {
        return Ok(None);
    }
    let value = serde_json::from_slice(&output.stdout)
        .map_err(|error| ServiceError::Storage(format!("invalid config JSON at {path}: {error}")))?;
    Ok(Some(value))
}

pub fn config_list_json(repo: &Path, category: &str) -> ServiceResult<Vec<serde_json::Value>> {
    let repo = repository_root(repo)?;
    let Some(head) = optional_revision(&repo, CONFIG_REF)? else { return Ok(Vec::new()); };
    config_list_json_at(&repo, category, &head)
}

pub fn config_list_json_at(
    repo: &Path,
    category: &str,
    revision_spec: &str,
) -> ServiceResult<Vec<serde_json::Value>> {
    let repo = repository_root(repo)?;
    let category = config_category(category)?;
    let revision = revision(&repo, revision_spec)?;
    let prefix = format!("{category}/");
    let output = git(&repo, ["ls-tree", "-r", "--name-only", revision.as_str(), "--", prefix.as_str()])?;
    let mut records = Vec::new();
    for path in text(&output).lines().map(str::trim).filter(|line| !line.is_empty()) {
        if !path.ends_with(".json") { continue; }
        let spec = format!("{revision}:{path}");
        let bytes = git(&repo, ["show", spec.as_str()])?.stdout;
        let value = serde_json::from_slice(&bytes)
            .map_err(|error| ServiceError::Storage(format!("invalid config JSON at {path}: {error}")))?;
        records.push(value);
    }
    Ok(records)
}

pub fn config_upsert_json(
    repo: &Path,
    category: &str,
    identity: &str,
    value: &serde_json::Value,
    message: &str,
) -> ServiceResult<CommitId> {
    let repo = repository_root(repo)?;
    let category = config_category(category)?;
    let identity = ref_component("config identity", identity)?;
    let path = format!("{category}/{identity}.json");
    let mut bytes = serde_json::to_vec_pretty(value)
        .map_err(|error| ServiceError::InvalidInput(error.to_string()))?;
    bytes.push(b'\n');
    mutate_config(&repo, message, |index| {
        let blob = hash_bytes(&repo, &bytes)?;
        git_with_env(&repo, ["update-index", "--add", "--cacheinfo", "100644", blob.as_str(), path.as_str()], index)?;
        Ok(())
    })
}

pub fn config_replace_json(
    repo: &Path,
    category: &str,
    records: &[(String, serde_json::Value)],
    message: &str,
) -> ServiceResult<Option<CommitId>> {
    let repo = repository_root(repo)?;
    let category = config_category(category)?;
    for _ in 0..4 {
        let expected = optional_revision(&repo, CONFIG_REF)?;
        let temporary_index = temporary_index_path();
        let result = (|| {
            if let Some(old) = expected.as_deref() {
                git_with_env(&repo, ["read-tree", old], &temporary_index)?;
                let prefix = format!("{category}/");
                let listing = git(&repo, ["ls-tree", "-r", "--name-only", old, "--", prefix.as_str()])?;
                for path in text(&listing).lines().map(str::trim).filter(|line| !line.is_empty()) {
                    git_with_env(&repo, ["update-index", "--force-remove", "--", path], &temporary_index)?;
                }
            } else {
                git_with_env(&repo, ["read-tree", "--empty"], &temporary_index)?;
            }
            for (identity, value) in records {
                let identity = ref_component("config identity", identity)?;
                let path = format!("{category}/{identity}.json");
                let mut bytes = serde_json::to_vec_pretty(value)
                    .map_err(|error| ServiceError::InvalidInput(error.to_string()))?;
                bytes.push(b'\n');
                let blob = hash_bytes(&repo, &bytes)?;
                git_with_env(&repo, ["update-index", "--add", "--cacheinfo", "100644", blob.as_str(), path.as_str()], &temporary_index)?;
            }
            let tree = text(&git_with_env(&repo, ["write-tree"], &temporary_index)?).trim().to_string();
            if let Some(old) = expected.as_deref() {
                let old_tree = text(&git(&repo, ["show", "-s", "--format=%T", old])?).trim().to_string();
                if tree == old_tree { return Ok(None); }
            }
            let commit = commit_tree(&repo, &tree, expected.as_deref(), message)?;
            let expected_ref = expected.as_deref().unwrap_or("0000000000000000000000000000000000000000");
            let update = git_status_output(&repo, ["update-ref", "-m", "AutoScribe config ledger", CONFIG_REF, commit.as_str(), expected_ref])?;
            if !update.status.success() { return Err(ServiceError::Conflict("config ledger advanced concurrently".into())); }
            Ok(Some(CommitId(commit)))
        })();
        let _ = fs::remove_file(&temporary_index);
        match result {
            Err(ServiceError::Conflict(message)) if message.contains("advanced concurrently") => continue,
            other => return other,
        }
    }
    Err(ServiceError::Conflict("config ledger remained busy after retries".into()))
}

pub fn mark_config_synced(repo: &Path, commit: &str) -> ServiceResult<()> {
    let repo = repository_root(repo)?;
    let commit = revision(&repo, commit)?;
    git(&repo, ["update-ref", "-m", "AutoScribe config synchronized", CONFIG_SYNCED_REF, commit.as_str()])?;
    Ok(())
}

fn mutate_config<F>(repo: &Path, message: &str, mut change: F) -> ServiceResult<CommitId>
where F: FnMut(&Path) -> ServiceResult<()> {
    let message = one_line("config commit message", message)?;
    for _ in 0..4 {
        let old = optional_revision(repo, CONFIG_REF)?;
        let temporary_index = temporary_index_path();
        let result = (|| {
            if let Some(old) = old.as_deref() {
                git_with_env(repo, ["read-tree", old], &temporary_index)?;
            } else {
                git_with_env(repo, ["read-tree", "--empty"], &temporary_index)?;
            }
            change(&temporary_index)?;
            let tree = text(&git_with_env(repo, ["write-tree"], &temporary_index)?).trim().to_string();
            if let Some(old) = old.as_deref() {
                let old_tree = text(&git(repo, ["show", "-s", "--format=%T", old])?).trim().to_string();
                if tree == old_tree { return Ok(CommitId(old.to_string())); }
            }
            let commit = commit_tree(repo, &tree, old.as_deref(), &message)?;
            let expected = old.as_deref().unwrap_or("0000000000000000000000000000000000000000");
            let update = git_status_output(repo, ["update-ref", "-m", "AutoScribe config ledger", CONFIG_REF, commit.as_str(), expected])?;
            if !update.status.success() { return Err(ServiceError::Conflict("config ledger advanced concurrently".into())); }
            Ok(CommitId(commit))
        })();
        let _ = fs::remove_file(&temporary_index);
        match result {
            Err(ServiceError::Conflict(message)) if message.contains("advanced concurrently") => continue,
            other => return other,
        }
    }
    Err(ServiceError::Conflict("config ledger remained busy after retries".into()))
}

fn config_payload_listing(repo: &Path, revision: Option<&str>) -> ServiceResult<String> {
    let Some(revision) = revision else { return Ok(String::new()); };
    let output = git(repo, ["ls-tree", "-r", revision, "--", "plans", "instructions"])?;
    Ok(text(&output))
}

fn config_submitted_ref(category: &str) -> ServiceResult<&'static str> {
    match category {
        "instructions" => Ok(CONFIG_INSTRUCTIONS_SUBMITTED_REF),
        "plans" => Ok(CONFIG_PLANS_SUBMITTED_REF),
        _ => Err(ServiceError::InvalidInput(format!("configuration category has no submitted ledger: {category}"))),
    }
}

fn config_category_listing(repo: &Path, category: &str, revision_spec: Option<&str>) -> ServiceResult<String> {
    let Some(revision_spec) = revision_spec else { return Ok(String::new()); };
    let revision = revision(repo, revision_spec)?;
    let prefix = format!("{category}/");
    let output = git(repo, ["ls-tree", "-r", revision.as_str(), "--", prefix.as_str()])?;
    Ok(text(&output))
}

fn config_category(value: &str) -> ServiceResult<String> {
    let value = one_line("config category", value)?;
    if !matches!(value.as_str(), "plans" | "instructions" | "state") {
        return Err(ServiceError::InvalidInput(format!("invalid config category: {value}")));
    }
    Ok(value)
}

pub fn last_commit(repo: &Path, path: &Path) -> ServiceResult<Option<(String, String, i64)>> {
    let repo = repository_root(repo)?;
    let path = safe_relative_path(path)?;
    let output = git_status_output(
        &repo,
        ["log", "-1", "--format=%H%x1f%s%x1f%ct", "--", path.as_str()],
    )?;
    if !output.status.success() || text(&output).trim().is_empty() { return Ok(None); }
    let value = text(&output);
    let mut parts = value.trim().splitn(3, '\u{1f}');
    let hash = parts.next().unwrap_or_default().to_string();
    let subject = parts.next().unwrap_or_default().to_string();
    let timestamp = parts.next().unwrap_or("0").parse().unwrap_or(0);
    Ok(Some((hash, subject, timestamp)))
}

pub fn status_code(repo: &Path, path: &Path) -> ServiceResult<String> {
    let repo = repository_root(repo)?;
    let path = safe_relative_path(path)?;
    Ok(text(&git(&repo, ["status", "--porcelain=v1", "--", path.as_str()])?)
        .trim().to_string())
}

pub fn worktree_blob(repo: &Path, path: &Path) -> ServiceResult<String> {
    let repo = repository_root(repo)?;
    let path = safe_relative_path(path)?;
    let bytes = fs::read(repo.join(path)).map_err(io)?;
    hash_bytes(&repo, &bytes)
}

pub fn file_history(repo: &Path, path: &Path) -> ServiceResult<Vec<(String, String, String, String)>> {
    let repo = repository_root(repo)?;
    let path = safe_relative_path(path)?;
    let output = git(&repo, ["log", "--all", "--follow", "--date=iso-strict", "--format=%H%x1f%ad%x1f%an%x1f%s", "--", path.as_str()])?;
    Ok(text(&output).lines().filter_map(|line| {
        let mut p = line.splitn(4, '\u{1f}');
        Some((p.next()?.into(), p.next()?.into(), p.next()?.into(), p.next()?.into()))
    }).collect())
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileStash {
    pub id: String,
    pub vault_path: String,
    pub repo_path: String,
    pub blob: String,
    pub reference: String,
    pub head: String,
    pub created_at: String,
}

#[derive(Default, Serialize, Deserialize)]
struct StashManifest { version: u32, items: Vec<FileStash> }

pub fn list_file_stashes(repo: &Path, path: Option<&Path>) -> ServiceResult<Vec<FileStash>> {
    let repo = repository_root(repo)?;
    let wanted = path.map(safe_relative_path).transpose()?;
    let mut items = read_stash_manifest(&repo)?.items;
    if let Some(wanted) = wanted { items.retain(|item| item.repo_path == wanted); }
    items.sort_by(|a, b| b.created_at.cmp(&a.created_at));
    Ok(items)
}

pub fn stash_file(repo: &Path, path: &Path) -> ServiceResult<FileStash> {
    let repo = repository_root(repo)?;
    let path = safe_relative_path(path)?;
    let bytes = fs::read(repo.join(&path)).map_err(io)?;
    let blob = hash_bytes(&repo, &bytes)?;
    let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default();
    let id = format!("{}-{}", now.as_secs(), &blob[..8]);
    let reference = format!("refs/autoscribe/file-stashes/{id}");
    git(&repo, ["update-ref", reference.as_str(), blob.as_str()])?;
    let item = FileStash {
        id, vault_path: path.clone(), repo_path: path, blob, reference,
        head: revision(&repo, "HEAD")?, created_at: now.as_secs().to_string(),
    };
    let mut manifest = read_stash_manifest(&repo)?;
    manifest.items.push(item.clone());
    write_stash_manifest(&repo, &manifest)?;
    Ok(item)
}

pub fn restore_file_stash(repo: &Path, path: &Path, id: &str) -> ServiceResult<FileStash> {
    let repo = repository_root(repo)?;
    let path = safe_relative_path(path)?;
    let item = read_stash_manifest(&repo)?.items.into_iter()
        .find(|item| item.id == id && item.repo_path == path)
        .ok_or_else(|| ServiceError::InvalidInput("file stash does not exist".into()))?;
    let bytes = git(&repo, ["cat-file", "blob", item.blob.as_str()])?.stdout;
    fs::write(repo.join(&path), bytes).map_err(io)?;
    git(&repo, ["add", "--", path.as_str()])?;
    Ok(item)
}

pub fn drop_file_stash(repo: &Path, path: &Path, id: &str) -> ServiceResult<FileStash> {
    let repo = repository_root(repo)?;
    let path = safe_relative_path(path)?;
    let mut manifest = read_stash_manifest(&repo)?;
    let position = manifest.items.iter().position(|item| item.id == id && item.repo_path == path)
        .ok_or_else(|| ServiceError::InvalidInput("file stash does not exist".into()))?;
    let item = manifest.items.remove(position);
    git(&repo, ["update-ref", "-d", item.reference.as_str()])?;
    write_stash_manifest(&repo, &manifest)?;
    Ok(item)
}

pub fn restore_file_to_index(repo: &Path, path: &Path, source: &str) -> ServiceResult<(String, String)> {
    let repo = repository_root(repo)?;
    let path = safe_relative_path(path)?;
    if !status_code(&repo, Path::new(&path))?.is_empty() {
        return Err(ServiceError::Conflict("file has uncommitted changes".into()));
    }
    let source = revision(&repo, source)?;
    let head = revision(&repo, "HEAD")?;
    let stamp = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();
    let safety = format!("refs/tags/autoscribe/file-restore/{stamp}-{}", &head[..8]);
    git(&repo, ["update-ref", safety.as_str(), head.as_str()])?;
    let bytes = git(&repo, ["show", format!("{source}:{path}").as_str()])?.stdout;
    fs::write(repo.join(&path), bytes).map_err(io)?;
    git(&repo, ["add", "--", path.as_str()])?;
    Ok((source, safety.trim_start_matches("refs/tags/").to_string()))
}

pub fn read_version(repo: &Path, request: VersionRequest) -> ServiceResult<Vec<u8>> {
    let repo = repository_root(repo)?;
    let path = safe_relative_path(&request.path)?;
    let revision = revision(&repo, &request.revision)?;
    Ok(git(&repo, ["show", format!("{revision}:{path}").as_str()])?.stdout)
}

pub fn restore_version(repo: &Path, request: RestoreRequest) -> ServiceResult<CommitId> {
    let repo = repository_root(repo)?;
    let path = safe_relative_path(&request.version.path)?;
    let expected = format!("RESTORE {path} FROM {}", request.version.revision);
    if request.confirmation != expected {
        return Err(ServiceError::InvalidInput(format!(
            "restore confirmation must be exactly: {expected}"
        )));
    }
    let bytes = read_version(&repo, request.version.clone())?;
    fs::write(repo.join(&path), bytes).map_err(io)?;
    commit(
        &repo,
        CommitRequest {
            paths: vec![PathBuf::from(&path)],
            message: format!("Restore {path} from {}", request.version.revision),
            purpose: CommitPurpose::Restore,
        },
    )
}

fn repository_root(repo: &Path) -> ServiceResult<PathBuf> {
    let requested = repo.canonicalize().map_err(io)?;
    if !requested.is_dir() {
        return Err(ServiceError::InvalidInput(
            "Git repository path is not a directory".into(),
        ));
    }
    let root = text(&git_unchecked(
        &requested,
        ["rev-parse", "--show-toplevel"],
    )?)
    .trim()
    .to_string();
    let root = PathBuf::from(root).canonicalize().map_err(io)?;
    if root != requested {
        return Err(ServiceError::InvalidInput(format!(
            "repository path must be the Git root: {}",
            root.display()
        )));
    }
    Ok(root)
}

fn safe_relative_path(path: &Path) -> ServiceResult<String> {
    if path.as_os_str().is_empty() || path.is_absolute() {
        return Err(ServiceError::InvalidInput(
            "Git path must be non-empty and relative".into(),
        ));
    }
    if path
        .components()
        .any(|part| !matches!(part, Component::Normal(_)))
    {
        return Err(ServiceError::InvalidInput(format!(
            "Git path is not normalized: {}",
            path.display()
        )));
    }
    Ok(path.to_string_lossy().replace('\\', "/"))
}

fn ref_component(label: &str, value: &str) -> ServiceResult<String> {
    let value = one_line(label, value)?;
    if value.starts_with('.')
        || value.ends_with('.')
        || value.contains("..")
        || !value
            .chars()
            .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '-' | '_' | '.'))
    {
        return Err(ServiceError::InvalidInput(format!(
            "invalid {label}: {value}"
        )));
    }
    Ok(value)
}

fn one_line(label: &str, value: &str) -> ServiceResult<String> {
    let value = value.trim();
    if value.is_empty() || value.contains(['\n', '\r', '\t']) {
        return Err(ServiceError::InvalidInput(format!(
            "{label} must be a non-empty single line"
        )));
    }
    Ok(value.to_string())
}

fn revision(repo: &Path, value: &str) -> ServiceResult<String> {
    let value = one_line("Git revision", value)?;
    Ok(text(&git(
        repo,
        [
            "rev-parse",
            "--verify",
            format!("{value}^{{commit}}").as_str(),
        ],
    )?)
    .trim()
    .to_string())
}

fn optional_revision(repo: &Path, value: &str) -> ServiceResult<Option<String>> {
    let output = git_status_output(repo, ["rev-parse", "--verify", value])?;
    if output.status.success() {
        return Ok(Some(text(&output).trim().to_string()));
    }
    if output.status.code() == Some(128) {
        return Ok(None);
    }
    Err(command_error(&output))
}

fn purpose_name(purpose: &CommitPurpose) -> &'static str {
    match purpose {
        CommitPurpose::Version => "version",
        CommitPurpose::Lock => "lock",
        CommitPurpose::WritebackCheckpoint => "writeback-checkpoint",
        CommitPurpose::DispatchWriteback => "dispatch-writeback",
        CommitPurpose::Restore => "restore",
    }
}

fn git<I, S>(repo: &Path, args: I) -> ServiceResult<Output>
where
    I: IntoIterator<Item = S>,
    S: AsRef<OsStr>,
{
    let output = git_status_output(repo, args)?;
    if output.status.success() {
        Ok(output)
    } else {
        Err(command_error(&output))
    }
}

fn git_unchecked<I, S>(repo: &Path, args: I) -> ServiceResult<Output>
where
    I: IntoIterator<Item = S>,
    S: AsRef<OsStr>,
{
    git(repo, args)
}

fn git_status<I, S>(repo: &Path, args: I) -> ServiceResult<std::process::ExitStatus>
where
    I: IntoIterator<Item = S>,
    S: AsRef<OsStr>,
{
    Ok(git_status_output(repo, args)?.status)
}

fn git_status_output<I, S>(repo: &Path, args: I) -> ServiceResult<Output>
where
    I: IntoIterator<Item = S>,
    S: AsRef<OsStr>,
{
    Command::new(GIT)
        .args(args)
        .current_dir(repo)
        .output()
        .map_err(io)
}

fn temporary_index_path() -> PathBuf {
    let nanos = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default().as_nanos();
    std::env::temp_dir().join(format!("autoscribe-index-{}-{nanos}", std::process::id()))
}

fn git_with_env<I, S>(repo: &Path, args: I, index: &Path) -> ServiceResult<Output>
where I: IntoIterator<Item = S>, S: AsRef<OsStr> {
    let output = Command::new(GIT).args(args).current_dir(repo)
        .env("GIT_INDEX_FILE", index).output().map_err(io)?;
    if output.status.success() { Ok(output) } else { Err(command_error(&output)) }
}

fn hash_bytes(repo: &Path, bytes: &[u8]) -> ServiceResult<String> {
    let mut child = Command::new(GIT).args(["hash-object", "-w", "--stdin"])
        .current_dir(repo).stdin(std::process::Stdio::piped()).stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped()).spawn().map_err(io)?;
    child.stdin.take().ok_or_else(|| ServiceError::Io("Git stdin unavailable".into()))?
        .write_all(bytes).map_err(io)?;
    let output = child.wait_with_output().map_err(io)?;
    if !output.status.success() { return Err(command_error(&output)); }
    Ok(text(&output).trim().to_string())
}

fn commit_tree(repo: &Path, tree: &str, parent: Option<&str>, message: &str) -> ServiceResult<String> {
    let mut command = Command::new(GIT);
    command.arg("commit-tree").arg(tree);
    if let Some(parent) = parent { command.args(["-p", parent]); }
    let mut child = command.current_dir(repo).stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped()).stderr(std::process::Stdio::piped())
        .spawn().map_err(io)?;
    child.stdin.take().ok_or_else(|| ServiceError::Io("Git stdin unavailable".into()))?
        .write_all(message.as_bytes()).map_err(io)?;
    let output = child.wait_with_output().map_err(io)?;
    if !output.status.success() { return Err(command_error(&output)); }
    Ok(text(&output).trim().to_string())
}

fn stash_manifest_path(repo: &Path) -> ServiceResult<PathBuf> {
    let raw = text(&git(repo, ["rev-parse", "--git-dir"])?).trim().to_string();
    let directory = PathBuf::from(raw);
    Ok(if directory.is_absolute() { directory } else { repo.join(directory) }
        .join("autoscribe-file-stashes.json"))
}

fn read_stash_manifest(repo: &Path) -> ServiceResult<StashManifest> {
    let path = stash_manifest_path(repo)?;
    if !path.exists() { return Ok(StashManifest { version: 1, items: Vec::new() }); }
    let bytes = fs::read(path).map_err(io)?;
    serde_json::from_slice(&bytes).map_err(|error| ServiceError::Io(error.to_string()))
}

fn write_stash_manifest(repo: &Path, manifest: &StashManifest) -> ServiceResult<()> {
    let bytes = serde_json::to_vec_pretty(manifest).map_err(|error| ServiceError::Io(error.to_string()))?;
    fs::write(stash_manifest_path(repo)?, bytes).map_err(io)
}

fn command_error(output: &Output) -> ServiceError {
    let detail = String::from_utf8_lossy(&output.stderr).trim().to_string();
    ServiceError::Io(if detail.is_empty() {
        format!("Git exited with {}", output.status)
    } else {
        detail
    })
}

fn text(output: &Output) -> String {
    String::from_utf8_lossy(&output.stdout).into_owned()
}

fn io(error: impl std::fmt::Display) -> ServiceError {
    ServiceError::Io(error.to_string())
}
