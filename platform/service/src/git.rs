use crate::{ServiceError, ServiceResult, types::*};
use std::{
    ffi::OsStr,
    fs,
    io::Write,
    path::{Component, Path, PathBuf},
    process::{Command, Output},
};

const GIT: &str = "/usr/bin/git";
const INFLIGHT_REF: &str = "refs/heads/autoscribe/inflight";

pub fn root(path: &Path) -> ServiceResult<PathBuf> {
    repository_root(path)
}

pub fn head(repo: &Path) -> ServiceResult<CommitId> {
    let repo = repository_root(repo)?;
    Ok(CommitId(revision(&repo, "HEAD")?))
}

/// Append the exact dispatch source bytes to the AutoScribe inflight history
/// without checking out, moving, or writing the user's master branch.
pub fn append_inflight_snapshot(
    repo: &Path,
    request: &LedgerSnapshotRequest,
) -> ServiceResult<LedgerSnapshot> {
    let repo = repository_root(repo)?;
    let dispatch = ref_component("dispatch identity", &request.dispatch.0)?;
    let plan = one_line("plan identity", &request.plan.0)?;
    if request.sources.is_empty() {
        return Err(ServiceError::InvalidInput(
            "ledger snapshot requires source files".into(),
        ));
    }

    for _ in 0..4 {
        let old = optional_revision(&repo, INFLIGHT_REF)?;
        let base = old.clone().unwrap_or(revision(&repo, "master")?);
        let temporary_index = temporary_index_path();
        let result = (|| {
            git_with_env(&repo, ["read-tree", base.as_str()], &temporary_index)?;
            let mut blobs = Vec::new();
            for source in &request.sources {
                let path = safe_relative_path(&source.path)?;
                let blob = hash_bytes(&repo, &source.bytes)?;
                git_with_env(
                    &repo,
                    [
                        "update-index",
                        "--add",
                        "--cacheinfo",
                        "100644",
                        blob.as_str(),
                        path.as_str(),
                    ],
                    &temporary_index,
                )?;
                blobs.push((PathBuf::from(path), blob));
            }
            let tree = text(&git_with_env(&repo, ["write-tree"], &temporary_index)?)
                .trim()
                .to_string();
            let mut message =
                format!("AUTOSCRIBE INFLIGHT {dispatch}\n\nDispatch: {dispatch}\nPlan: {plan}");
            for source in &request.sources {
                message.push_str(&format!(
                    "\nRecord: {}\t{}",
                    one_line("record slug", &source.slug)?,
                    safe_relative_path(&source.path)?
                ));
            }
            let commit = commit_tree(&repo, &tree, old.as_deref(), &message)?;
            let expected = old
                .as_deref()
                .unwrap_or("0000000000000000000000000000000000000000");
            let update = git_status_output(
                &repo,
                [
                    "update-ref",
                    "-m",
                    "AutoScribe inflight ledger",
                    INFLIGHT_REF,
                    commit.as_str(),
                    expected,
                ],
            )?;
            if !update.status.success() {
                return Err(ServiceError::Conflict(
                    "inflight ledger advanced concurrently".into(),
                ));
            }
            Ok(LedgerSnapshot {
                reference: INFLIGHT_REF.into(),
                commit: CommitId(commit),
                blobs,
            })
        })();
        let _ = fs::remove_file(&temporary_index);
        match result {
            Err(ServiceError::Conflict(message)) if message.contains("advanced concurrently") => {
                continue;
            }
            other => return other,
        }
    }
    Err(ServiceError::Conflict(
        "inflight ledger remained busy after retries".into(),
    ))
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
        return Err(ServiceError::InvalidInput(
            "response outcome must be saved, accepted, or declined".into(),
        ));
    }
    for _ in 0..4 {
        let old = optional_revision(&repo, INFLIGHT_REF)?
            .ok_or_else(|| ServiceError::Conflict("inflight ledger does not exist".into()))?;
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
                return Err(ServiceError::Conflict(
                    "inflight ledger advanced concurrently".into(),
                ));
            }
            Ok(CommitId(commit))
        })();
        let _ = fs::remove_file(&temporary_index);
        match attempt {
            Err(ServiceError::Conflict(message)) if message.contains("advanced concurrently") => {
                continue;
            }
            other => return other,
        }
    }
    Err(ServiceError::Conflict(
        "inflight ledger remained busy after retries".into(),
    ))
}

pub fn append_dispatch_event(
    repo: &Path,
    dispatch: &str,
    outcome: &str,
    reason: Option<&str>,
) -> ServiceResult<CommitId> {
    let repo = repository_root(repo)?;
    let dispatch = one_line("dispatch identity", dispatch)?;
    if !matches!(outcome, "submitted" | "completed" | "failed" | "cancelled") {
        return Err(ServiceError::InvalidInput(
            "dispatch outcome must be submitted, completed, failed, or cancelled".into(),
        ));
    }
    for _ in 0..4 {
        let old = optional_revision(&repo, INFLIGHT_REF)?
            .ok_or_else(|| ServiceError::Conflict("inflight ledger does not exist".into()))?;
        let tree = text(&git(&repo, ["show", "-s", "--format=%T", old.as_str()])?)
            .trim()
            .to_string();
        let mut message =
            format!("AUTOSCRIBE DISPATCH {outcome}\n\nDispatch: {dispatch}\nOutcome: {outcome}");
        if let Some(reason) = reason {
            message.push_str(&format!(
                "\nReason: {}",
                one_line("dispatch reason", reason)?
            ));
        }
        let commit = commit_tree(&repo, &tree, Some(&old), &message)?;
        let update = git_status_output(
            &repo,
            [
                "update-ref",
                "-m",
                "AutoScribe dispatch event",
                INFLIGHT_REF,
                commit.as_str(),
                old.as_str(),
            ],
        )?;
        if update.status.success() {
            return Ok(CommitId(commit));
        }
    }
    Err(ServiceError::Conflict(
        "inflight ledger remained busy after retries".into(),
    ))
}

pub fn read_version(repo: &Path, request: VersionRequest) -> ServiceResult<Vec<u8>> {
    let repo = repository_root(repo)?;
    let path = safe_relative_path(&request.path)?;
    let revision = revision(&repo, &request.revision)?;
    Ok(git(&repo, ["show", format!("{revision}:{path}").as_str()])?.stdout)
}

fn repository_root(repo: &Path) -> ServiceResult<PathBuf> {
    let requested = repo.canonicalize().map_err(io)?;
    if !requested.is_dir() {
        return Err(ServiceError::InvalidInput(
            "Git repository path is not a directory".into(),
        ));
    }
    let root = text(&git(&requested, ["rev-parse", "--show-toplevel"])?)
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
        || !value.chars().all(|character| {
            character.is_ascii_alphanumeric() || matches!(character, '-' | '_' | '.')
        })
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
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    std::env::temp_dir().join(format!("autoscribe-index-{}-{nanos}", std::process::id()))
}

fn git_with_env<I, S>(repo: &Path, args: I, index: &Path) -> ServiceResult<Output>
where
    I: IntoIterator<Item = S>,
    S: AsRef<OsStr>,
{
    let output = Command::new(GIT)
        .args(args)
        .current_dir(repo)
        .env("GIT_INDEX_FILE", index)
        .output()
        .map_err(io)?;
    if output.status.success() {
        Ok(output)
    } else {
        Err(command_error(&output))
    }
}

fn hash_bytes(repo: &Path, bytes: &[u8]) -> ServiceResult<String> {
    let mut child = Command::new(GIT)
        .args(["hash-object", "-w", "--stdin"])
        .current_dir(repo)
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .map_err(io)?;
    child
        .stdin
        .take()
        .ok_or_else(|| ServiceError::Io("Git stdin unavailable".into()))?
        .write_all(bytes)
        .map_err(io)?;
    let output = child.wait_with_output().map_err(io)?;
    if !output.status.success() {
        return Err(command_error(&output));
    }
    Ok(text(&output).trim().to_string())
}

fn commit_tree(
    repo: &Path,
    tree: &str,
    parent: Option<&str>,
    message: &str,
) -> ServiceResult<String> {
    let mut command = Command::new(GIT);
    command.arg("commit-tree").arg(tree);
    if let Some(parent) = parent {
        command.args(["-p", parent]);
    }
    let mut child = command
        .current_dir(repo)
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .map_err(io)?;
    child
        .stdin
        .take()
        .ok_or_else(|| ServiceError::Io("Git stdin unavailable".into()))?
        .write_all(message.as_bytes())
        .map_err(io)?;
    let output = child.wait_with_output().map_err(io)?;
    if !output.status.success() {
        return Err(command_error(&output));
    }
    Ok(text(&output).trim().to_string())
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
