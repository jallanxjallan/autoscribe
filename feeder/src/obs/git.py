from __future__ import annotations

from pathlib import Path

from .errors import ObsError
from .process import run


def root(cwd: Path) -> Path:
    value = run(["git", "rev-parse", "--show-toplevel"], cwd=cwd).stdout.strip()
    if not value:
        raise ObsError("could not resolve git root")
    return Path(value).resolve()


def head(repo: Path) -> str:
    return run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()


def dirty_files(repo: Path) -> list[str]:
    output = run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=repo
    ).stdout
    entries = [entry for entry in output.split("\0") if entry]
    paths: list[str] = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        status, value = entry[:2], entry[3:].strip()
        if status.find("R") >= 0 or status.find("C") >= 0:
            if value:
                paths.append(value)
            index += 2
        else:
            if value:
                paths.append(value)
            index += 1
    return sorted(set(paths))


def dirty_tracked_files(repo: Path) -> set[str]:
    output = run(
        ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", "HEAD"], cwd=repo
    ).stdout
    return {line.strip() for line in output.splitlines() if line.strip()}


def last_commit(repo: Path, relpath: str) -> str:
    result = run(
        ["git", "log", "--max-count=1", "--format=%H", "--", relpath],
        cwd=repo,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""



def last_commit_record(repo: Path, relpath: str) -> dict[str, object] | None:
    separator = "\x1f"
    result = run(
        [
            "git", "log", "--max-count=1",
            f"--format=%H{separator}%s{separator}%ct", "--", relpath,
        ],
        cwd=repo,
        check=False,
    )
    value = result.stdout.strip()
    if result.returncode != 0 or not value:
        return None
    parts = value.split(separator, 2)
    if len(parts) != 3:
        return None
    commit_hash, subject, timestamp = parts
    return {
        "hash": commit_hash,
        "short_hash": commit_hash[:8],
        "subject": subject,
        "timestamp": int(timestamp),
    }

def commit_files(repo: Path, paths: list[str], message: str, body: str = "") -> str:
    if not paths:
        raise ObsError("cannot commit an empty file list")
    run(["git", "add", "--", *paths], cwd=repo)
    args = ["git", "commit", "--only", "--allow-empty", "-m", message]
    if body:
        args.extend(["-m", body])
    args.extend(["--", *paths])
    run(args, cwd=repo)
    return head(repo)


def status_records(repo: Path) -> list[dict[str, str]]:
    output = run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=repo).stdout
    entries = [entry for entry in output.split("\0") if entry]
    records: list[dict[str, str]] = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        status = entry[:2]
        value = entry[3:].strip()
        record = {"path": value, "index": status[0], "worktree": status[1], "status": status}
        if "R" in status or "C" in status:
            if index + 1 < len(entries):
                record["renamed_from"] = entries[index + 1]
            index += 2
        else:
            index += 1
        records.append(record)
    return records


def file_state(repo: Path, relpath: str) -> dict[str, object]:
    records = [record for record in status_records(repo) if record["path"] == relpath]
    commit = last_commit(repo, relpath)
    if not records:
        state = "clean" if commit else "untracked"
        status = ""
    else:
        status = records[0]["status"]
        state = "untracked" if status == "??" else "dirty"
    return {
        "repo_state": state,
        "git_status": status,
        "git_commit": commit or None,
        "short_commit": commit[:8] if commit else None,
        "has_prior_commit": bool(commit),
    }

_AUTOSCRIBE_SUBJECT_PREFIXES = (
    "UPLOAD ",
    "WRITEBACK",
    "AUTOSCRIBE ",
    "AUTOSCRIBE:",
    "PIPELINE ",
    "PIPELINE:",
)


def user_commits(repo: Path, *, limit: int = 100) -> list[dict[str, object]]:
    """Return recent commits that were not created by AutoScribe operations."""
    if limit < 1:
        raise ObsError("commit list limit must be positive")
    separator = "\x1f"
    record_separator = "\x1e"
    output = run(
        [
            "git", "log", f"--max-count={limit}",
            f"--format=%H{separator}%h{separator}%s{separator}%ct{record_separator}",
        ],
        cwd=repo,
    ).stdout
    commits: list[dict[str, object]] = []
    for raw in output.split(record_separator):
        raw = raw.strip()
        if not raw:
            continue
        parts = raw.split(separator)
        if len(parts) != 4:
            continue
        commit_hash, short_hash, subject, timestamp = parts
        if subject.upper().startswith(tuple(prefix.upper() for prefix in _AUTOSCRIBE_SUBJECT_PREFIXES)):
            continue
        files = files_in_commit(repo, commit_hash)
        if not files:
            continue
        tags = inflight_tags(repo, commit_hash)
        if tags:
            continue
        commits.append({
            "hash": commit_hash,
            "short_hash": short_hash,
            "subject": subject,
            "timestamp": int(timestamp),
            "files": files,
            "count": len(files),
            "inflight": False,
            "inflight_tags": [],
        })
    return commits


def files_in_commit(repo: Path, commit_hash: str) -> list[str]:
    """Return files introduced or changed by one commit, including a root commit."""
    value = str(commit_hash or "").strip()
    if not value:
        raise ObsError("commit hash is required")
    output = run(
        [
            "git", "diff-tree", "--root", "--no-commit-id", "--name-only", "-r",
            "--diff-filter=ACMRT", value,
        ],
        cwd=repo,
    ).stdout
    return sorted({line.strip() for line in output.splitlines() if line.strip()})

_INFLIGHT_TAG_PREFIX = "inflight/"


def inflight_tags(repo: Path, commit_hash: str) -> list[str]:
    value = str(commit_hash or "").strip()
    if not value:
        raise ObsError("commit hash is required")
    output = run(["git", "tag", "--points-at", value], cwd=repo).stdout
    return sorted(
        line.strip() for line in output.splitlines()
        if line.strip().startswith(_INFLIGHT_TAG_PREFIX)
    )


def is_inflight(repo: Path, commit_hash: str) -> bool:
    return bool(inflight_tags(repo, commit_hash))


def tag_inflight(repo: Path, commit_hash: str, plan_slug: str, timestamp: str) -> str:
    commit = str(commit_hash or "").strip()
    plan = str(plan_slug or "").strip()
    stamp = str(timestamp or "").strip()
    if not commit:
        raise ObsError("commit hash is required")
    if not plan:
        raise ObsError("plan slug is required")
    if not stamp:
        raise ObsError("inflight timestamp is required")
    if is_inflight(repo, commit):
        raise ObsError(f"commit is already tagged inflight: {commit[:8]}")

    safe_stamp = f"{stamp[:10].replace('-', '')}T{stamp[11:19].replace(':', '')}{stamp[20:]}"
    tag_name = f"{_INFLIGHT_TAG_PREFIX}{plan}/{safe_stamp}"
    message = f"plan={plan}\ndispatched_at={stamp}\ncommit={commit}"
    run(["git", "tag", "-a", tag_name, commit, "-m", message], cwd=repo)
    return tag_name


def show_file(repo: Path, commit_hash: str, relpath: str) -> str:
    value = str(commit_hash or "").strip()
    path = str(relpath or "").strip()
    if not value or not path:
        raise ObsError("commit hash and path are required")
    result = run(["git", "show", f"{value}:{path}"], cwd=repo, check=False)
    if result.returncode != 0:
        raise ObsError(f"file is not available in commit {value[:8]}: {path}")
    return result.stdout


def commit_file_states(repo: Path, commit_hash: str) -> list[dict[str, object]]:
    files = files_in_commit(repo, commit_hash)
    head_hash = head(repo)
    states: list[dict[str, object]] = []
    for path in files:
        state = file_state(repo, path)
        latest = last_commit(repo, path)
        states.append({
            "path": path,
            "repo_state": state["repo_state"],
            "git_status": state["git_status"],
            "latest_commit": latest or None,
            "at_selected_commit": latest == commit_hash,
            "selected_commit": commit_hash,
            "head": head_hash,
        })
    return states

_WRITEBACK_SOURCE_TRAILER = "AutoScribe-Source-Commit"
_WRITEBACK_TAG_TRAILER = "AutoScribe-Inflight-Tag"


def inflight_commit_records(repo: Path, *, limit: int = 100) -> list[dict[str, object]]:
    """Return inflight-tagged commits that do not yet have a writeback commit."""
    if limit < 1:
        raise ObsError("commit list limit must be positive")
    output = run(
        ["git", "for-each-ref", "--sort=-creatordate",
         "--format=%(refname:short)\x1f%(*objectname)\x1f%(creatordate:unix)",
         "refs/tags/inflight/"],
        cwd=repo,
    ).stdout
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw in output.splitlines():
        parts = raw.split("\x1f")
        if len(parts) != 3:
            continue
        tag_name, commit_hash, tag_timestamp = parts
        if commit_hash in seen or has_writeback_commit(repo, commit_hash):
            continue
        seen.add(commit_hash)
        plan_slug = _plan_from_inflight_tag(tag_name)
        subject = run(["git", "show", "-s", "--format=%s", commit_hash], cwd=repo).stdout.strip()
        timestamp = run(["git", "show", "-s", "--format=%ct", commit_hash], cwd=repo).stdout.strip()
        files = files_in_commit(repo, commit_hash)
        records.append({
            "hash": commit_hash,
            "short_hash": commit_hash[:8],
            "subject": subject,
            "timestamp": int(timestamp or 0),
            "tag_timestamp": int(tag_timestamp or 0),
            "plan_slug": plan_slug,
            "inflight_tag": tag_name,
            "files": files,
            "count": len(files),
        })
        if len(records) >= limit:
            break
    return records


def _plan_from_inflight_tag(tag_name: str) -> str:
    value = str(tag_name or "")
    if not value.startswith(_INFLIGHT_TAG_PREFIX):
        return ""
    remainder = value[len(_INFLIGHT_TAG_PREFIX):]
    return remainder.rsplit("/", 1)[0] if "/" in remainder else remainder


def has_writeback_commit(repo: Path, source_commit: str) -> bool:
    source = str(source_commit or "").strip()
    if not source:
        raise ObsError("source commit is required")
    result = run(
        ["git", "log", "HEAD", "--format=%B%x1e", "--grep",
         f"^{_WRITEBACK_SOURCE_TRAILER}: {source}$"],
        cwd=repo,
        check=False,
    )
    return bool(result.stdout.strip()) if result.returncode == 0 else False


def writeback_commit(repo: Path, paths: list[str], *, source_commit: str,
                     inflight_tag: str, plan_slug: str) -> str:
    source = str(source_commit or "").strip()
    tag = str(inflight_tag or "").strip()
    plan = str(plan_slug or "").strip()
    if not source or not tag or not plan:
        raise ObsError("writeback commit requires source commit, inflight tag, and plan slug")
    if has_writeback_commit(repo, source):
        raise ObsError(f"dispatch commit already has a writeback commit: {source[:8]}")
    message = f"WRITEBACK {source[:8]}: {plan}"
    body = f"{_WRITEBACK_SOURCE_TRAILER}: {source}\n{_WRITEBACK_TAG_TRAILER}: {tag}"
    return commit_files(repo, paths, message, body)
