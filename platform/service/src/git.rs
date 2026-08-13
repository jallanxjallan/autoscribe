use crate::{ServiceError, ServiceResult, types::*};
use std::{
    ffi::OsStr,
    fs,
    path::{Component, Path, PathBuf},
    process::{Command, Output},
    time::{SystemTime, UNIX_EPOCH},
};

const GIT: &str = "/usr/bin/git";
const RUN_PREFIX: &str = "autoscribe/run/";
const DISPATCH_TAG_PREFIX: &str = "autoscribe/dispatch/";

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
    if status.success() {
        return Err(ServiceError::Conflict(
            "selected paths have no changes to commit".into(),
        ));
    }
    if status.code() != Some(1) {
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
    args.extend(paths);
    git(&repo, args)?;
    Ok(CommitId(revision(&repo, "HEAD")?))
}

pub fn create_dispatch_branch(
    repo: &Path,
    request: &CreateDispatchBranchRequest,
) -> ServiceResult<DispatchBranch> {
    let repo = repository_root(repo)?;
    let dispatch = ref_component("dispatch identity", &request.dispatch.0)?;
    let branch = format!("{RUN_PREFIX}{dispatch}");
    let source_revision = revision(&repo, &request.source_revision)?;
    validate_dispatch_request(request)?;
    let message = dispatch_message(request, &source_revision)?;

    if let Some(commit) = optional_revision(&repo, &format!("refs/heads/{branch}"))? {
        let existing_message = text(&git(&repo, ["show", "-s", "--format=%B", commit.as_str()])?);
        let parent = revision(&repo, &format!("{commit}^"))?;
        if existing_message.trim_end() == message.trim_end() && parent == source_revision {
            return Ok(DispatchBranch {
                name: branch,
                commit: CommitId(commit),
            });
        }
        return Err(ServiceError::Conflict(format!(
            "dispatch branch already exists with different metadata: {branch}"
        )));
    }

    let worktree = DispatchWorktree::create(&repo, &source_revision)?;
    git(&worktree.path, ["switch", "--quiet", "-c", branch.as_str()])?;
    let (subject, body) = message
        .split_once("\n\n")
        .ok_or_else(|| ServiceError::InvalidInput("dispatch message is incomplete".into()))?;
    git(
        &worktree.path,
        ["commit", "--allow-empty", "-m", subject, "-m", body],
    )?;
    let commit = revision(&worktree.path, "HEAD")?;
    Ok(DispatchBranch {
        name: branch,
        commit: CommitId(commit),
    })
}

pub fn tag_dispatch(repo: &Path, request: TagRequest) -> ServiceResult<String> {
    let repo = repository_root(repo)?;
    let dispatch = ref_component("dispatch identity", &request.dispatch.0)?;
    let commit = revision(&repo, &request.commit.0)?;
    let tag = format!("{DISPATCH_TAG_PREFIX}{dispatch}");
    if let Some(existing) = optional_revision(&repo, &format!("refs/tags/{tag}^{{}}"))? {
        if existing == commit {
            return Ok(tag);
        }
        return Err(ServiceError::Conflict(format!(
            "dispatch tag already points to another commit: {tag}"
        )));
    }
    let plan = one_line("plan identity", &request.plan.0)?;
    git(
        &repo,
        [
            "tag",
            "-a",
            tag.as_str(),
            commit.as_str(),
            "-m",
            format!("AutoScribe dispatch {dispatch}\nPlan: {plan}").as_str(),
        ],
    )?;
    Ok(tag)
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

fn validate_dispatch_request(request: &CreateDispatchBranchRequest) -> ServiceResult<()> {
    one_line("source branch", &request.source_branch)?;
    one_line("plan identity", &request.plan.0)?;
    one_line("plan version", &request.plan_version)?;
    one_line("payload SHA-256", &request.payload_sha256)?;
    if request.records.is_empty() {
        return Err(ServiceError::InvalidInput(
            "dispatch branch requires at least one source record".into(),
        ));
    }
    for record in &request.records {
        one_line("record slug", &record.slug)?;
        safe_relative_path(&record.path)?;
    }
    Ok(())
}

fn dispatch_message(
    request: &CreateDispatchBranchRequest,
    source_revision: &str,
) -> ServiceResult<String> {
    let mut lines = vec![
        format!(
            "Dispatch: {}",
            one_line("dispatch identity", &request.dispatch.0)?
        ),
        format!("Source-Revision: {source_revision}"),
        format!(
            "Source-Branch: {}",
            one_line("source branch", &request.source_branch)?
        ),
        format!("Plan: {}", one_line("plan identity", &request.plan.0)?),
        format!(
            "Plan-Version: {}",
            one_line("plan version", &request.plan_version)?
        ),
        format!(
            "Payload-SHA256: {}",
            one_line("payload SHA-256", &request.payload_sha256)?
        ),
    ];
    for record in &request.records {
        lines.push(format!(
            "Record: {}\t{}",
            one_line("record slug", &record.slug)?,
            safe_relative_path(&record.path)?
        ));
    }
    Ok(format!(
        "AUTOSCRIBE DISPATCH {}\n\n{}",
        request.dispatch.0,
        lines.join("\n")
    ))
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

struct DispatchWorktree {
    repo: PathBuf,
    path: PathBuf,
}

impl DispatchWorktree {
    fn create(repo: &Path, revision: &str) -> ServiceResult<Self> {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "autoscribe-dispatch-worktree-{}-{unique}",
            std::process::id()
        ));
        if path.exists() {
            return Err(ServiceError::Conflict(format!(
                "temporary worktree path already exists: {}",
                path.display()
            )));
        }
        git(
            repo,
            [
                "worktree",
                "add",
                "--quiet",
                "--detach",
                path.to_string_lossy().as_ref(),
                revision,
            ],
        )?;
        Ok(Self {
            repo: repo.to_path_buf(),
            path,
        })
    }
}

impl Drop for DispatchWorktree {
    fn drop(&mut self) {
        let _ = Command::new(GIT)
            .args(["worktree", "remove", "--force"])
            .arg(&self.path)
            .current_dir(&self.repo)
            .output();
        if self.path.starts_with(std::env::temp_dir()) {
            let _ = fs::remove_dir_all(&self.path);
        }
    }
}
