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
