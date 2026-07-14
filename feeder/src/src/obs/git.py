from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .errors import ObsError
from .process import run

AUTOSCRIBE_EVENT = "Autoscribe-Event"
AUTOSCRIBE_USER_COMMIT = "Autoscribe-User-Commit"
AUTOSCRIBE_PLAN = "Autoscribe-Plan"
AUTOSCRIBE_FILE = "Autoscribe-File"


@dataclass(frozen=True)
class CommitInfo:
    hash: str
    subject: str
    timestamp: int
    body: str = ""

    def as_dict(self) -> dict:
        return {
            "hash": self.hash,
            "subject": self.subject,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class WorktreeState:
    tracked: bool
    index: str
    worktree: str
    renamed_from: str | None = None

    @property
    def staged(self) -> bool:
        return self.index not in {" ", "?"}

    @property
    def modified(self) -> bool:
        return self.worktree not in {" ", "?"}

    @property
    def conflicted(self) -> bool:
        return self.index == "U" or self.worktree == "U" or (self.index + self.worktree) in {
            "AA", "DD", "AU", "UA", "DU", "UD", "UU",
        }

    @property
    def label(self) -> str:
        if self.conflicted:
            return "conflicted"
        if not self.tracked:
            return "untracked"
        if self.index == "D" or self.worktree == "D":
            return "deleted"
        if self.index == "R" or self.worktree == "R":
            return "renamed"
        if self.staged and self.modified:
            return "staged+modified"
        if self.staged:
            return "staged"
        if self.modified:
            return "modified"
        return "clean"

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "tracked": self.tracked,
            "staged": self.staged,
            "modified": self.modified,
            "conflicted": self.conflicted,
            "index": self.index,
            "worktree": self.worktree,
            "renamed_from": self.renamed_from,
        }


def root(cwd: Path) -> Path:
    value = run(["git", "rev-parse", "--show-toplevel"], cwd=cwd).stdout.strip()
    if not value:
        raise ObsError("could not resolve git root")
    return Path(value).resolve()


def head(repo: Path) -> str:
    result = run(["git", "rev-parse", "HEAD"], cwd=repo, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def ensure_operable(repo: Path) -> None:
    git_dir = Path(run(["git", "rev-parse", "--git-dir"], cwd=repo).stdout.strip())
    if not git_dir.is_absolute():
        git_dir = repo / git_dir
    blocked = [
        git_dir / "MERGE_HEAD",
        git_dir / "CHERRY_PICK_HEAD",
        git_dir / "REVERT_HEAD",
        git_dir / "rebase-merge",
        git_dir / "rebase-apply",
    ]
    active = [path.name for path in blocked if path.exists()]
    if active:
        raise ObsError(f"git operation already in progress: {', '.join(active)}")


def status_map(repo: Path) -> dict[str, WorktreeState]:
    output = run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=repo
    ).stdout
    entries = [entry for entry in output.split("\0") if entry]
    states: dict[str, WorktreeState] = {}
    index = 0
    while index < len(entries):
        entry = entries[index]
        xy = entry[:2]
        path = entry[3:]
        renamed_from = None
        if "R" in xy or "C" in xy:
            if index + 1 >= len(entries):
                raise ObsError("malformed git status rename entry")
            renamed_from = entries[index + 1]
            index += 1
        tracked = xy != "??"
        states[path] = WorktreeState(tracked, xy[0], xy[1], renamed_from)
        index += 1
    return states


def worktree_state(repo: Path, relpath: str, states: dict[str, WorktreeState] | None = None) -> WorktreeState:
    current = states if states is not None else status_map(repo)
    return current.get(relpath, WorktreeState(True, " ", " "))


def dirty_files(repo: Path) -> list[str]:
    return sorted(path for path, state in status_map(repo).items() if state.label != "clean")


def dirty_tracked_files(repo: Path) -> set[str]:
    return {path for path, state in status_map(repo).items() if state.tracked and state.label != "clean"}


def _commit(repo: Path, args: list[str], *, check: bool = True) -> CommitInfo | None:
    result = run(args, cwd=repo, check=check)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    values = result.stdout.rstrip("\n").split("\x1f", 3)
    if len(values) < 3:
        return None
    return CommitInfo(values[0], values[2], int(values[1]), values[3] if len(values) > 3 else "")


def latest_commit(repo: Path, relpath: str) -> CommitInfo | None:
    return _commit(
        repo,
        ["git", "log", "-1", "--format=%H%x1f%ct%x1f%s%x1f%B", "--", relpath],
        check=False,
    )


def last_commit(repo: Path, relpath: str) -> str:
    current = latest_commit(repo, relpath)
    return current.hash if current else ""


def trailers(body: str) -> dict[str, list[str]]:
    parsed: dict[str, list[str]] = {}
    for line in body.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key.startswith("Autoscribe-"):
            parsed.setdefault(key, []).append(value.strip())
    return parsed


def is_autoscribe_commit(info: CommitInfo) -> bool:
    return AUTOSCRIBE_EVENT in trailers(info.body)


def latest_user_commit(repo: Path, relpath: str) -> CommitInfo | None:
    result = run(
        ["git", "log", "--format=%H%x1f%ct%x1f%s%x1f%B%x1e", "--", relpath],
        cwd=repo,
        check=False,
    )
    for record in result.stdout.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        values = record.split("\x1f", 3)
        if len(values) < 3:
            continue
        info = CommitInfo(values[0], values[2], int(values[1]), values[3] if len(values) > 3 else "")
        if not is_autoscribe_commit(info):
            return info
    return None


def blob_hash(repo: Path, commit: str, relpath: str) -> str:
    result = run(["git", "rev-parse", f"{commit}:{relpath}"], cwd=repo, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def dispatch_events(repo: Path) -> list[CommitInfo]:
    result = run(
        ["git", "log", "--format=%H%x1f%ct%x1f%s%x1f%B%x1e"],
        cwd=repo,
        check=False,
    )
    events: list[CommitInfo] = []
    for record in result.stdout.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        values = record.split("\x1f", 3)
        if len(values) < 4:
            continue
        info = CommitInfo(values[0], values[2], int(values[1]), values[3])
        parsed = trailers(info.body)
        if parsed.get(AUTOSCRIBE_EVENT) == ["dispatch"]:
            events.append(info)
    return events


def _decode_file_trailer(value: str) -> tuple[str, str]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ObsError(f"invalid Autoscribe-File trailer: {value}") from exc
    path = str(payload.get("path") or "")
    blob = str(payload.get("blob") or "")
    if not path or not blob:
        raise ObsError(f"invalid Autoscribe-File trailer: {value}")
    return path, blob


def dispatch_state(repo: Path, relpath: str, latest: CommitInfo | None, events: list[CommitInfo]) -> dict:
    latest_blob = blob_hash(repo, latest.hash, relpath) if latest else ""
    for event in events:  # newest first
        parsed = trailers(event.body)
        for value in parsed.get(AUTOSCRIBE_FILE, []):
            path, expected_blob = _decode_file_trailer(value)
            if path != relpath:
                continue
            if latest and latest.timestamp > event.timestamp:
                return {
                    "state": "conflict",
                    "reason": "file_committed_after_dispatch",
                    "dispatch_commit": event.hash,
                }
            if latest_blob != expected_blob:
                return {
                    "state": "conflict",
                    "reason": "file_revision_mismatch",
                    "dispatch_commit": event.hash,
                }
            return {
                "state": "in-flight",
                "reason": None,
                "dispatch_commit": event.hash,
                "user_commit": (parsed.get(AUTOSCRIBE_USER_COMMIT) or [""])[0],
                "plan": (parsed.get(AUTOSCRIBE_PLAN) or [""])[0],
            }
    return {"state": "ready", "reason": None, "dispatch_commit": None}


def commit_files(
    repo: Path, paths: list[str], message: str, body: str = "", *, amend: bool = False
) -> str:
    ensure_operable(repo)
    paths = _validated_paths(repo, paths)
    message = message.strip()
    if not message:
        raise ObsError("git message is required")
    if amend:
        current = _commit(repo, ["git", "show", "-s", "--format=%H%x1f%ct%x1f%s%x1f%B", "HEAD"], check=False)
        if not current:
            raise ObsError("cannot amend before the first commit")
        if is_autoscribe_commit(current):
            raise ObsError("cannot amend an Autoscribe commit; return to the user grouping commit")
    run(["git", "add", "--", *paths], cwd=repo)
    args = ["git", "commit", "--only", "--allow-empty"]
    if amend:
        args.append("--amend")
    args.extend(["-m", message])
    if body:
        args.extend(["-m", body])
    args.extend(["--", *paths])
    run(args, cwd=repo)
    return head(repo)


def create_dispatch_commit(repo: Path, paths: list[str], user_commit: str, plan: str) -> str:
    ensure_operable(repo)
    paths = _validated_paths(repo, paths)
    if head(repo) != user_commit:
        raise ObsError("HEAD changed after the user grouping commit; return to Stage Files and recommit")
    states = status_map(repo)
    conflicts: list[dict[str, str]] = []
    events = dispatch_events(repo)
    file_trailers: list[str] = []
    for path in paths:
        state = worktree_state(repo, path, states)
        if state.label != "clean":
            conflicts.append({"path": path, "reason": f"worktree_{state.label}"})
            continue
        latest = latest_commit(repo, path)
        if not latest or latest.hash != user_commit:
            conflicts.append({"path": path, "reason": "not_in_user_commit"})
            continue
        current_dispatch = dispatch_state(repo, path, latest, events)
        if current_dispatch["state"] != "ready":
            conflicts.append({"path": path, "reason": current_dispatch["state"]})
            continue
        blob = blob_hash(repo, user_commit, path)
        file_trailers.append(json.dumps({"path": path, "blob": blob}, separators=(",", ":")))
    if conflicts:
        raise ObsError("dispatch conflicts:\n" + "\n".join(
            f"  {item['path']}: {item['reason']}" for item in conflicts
        ))
    message = f"Autoscribe dispatch: {plan}"
    body_lines = [
        f"{AUTOSCRIBE_EVENT}: dispatch",
        f"{AUTOSCRIBE_USER_COMMIT}: {user_commit}",
        f"{AUTOSCRIBE_PLAN}: {plan}",
    ]
    body_lines.extend(f"{AUTOSCRIBE_FILE}: {value}" for value in file_trailers)
    run(["git", "commit", "--allow-empty", "-m", message, "-m", "\n".join(body_lines)], cwd=repo)
    return head(repo)


def _validated_paths(repo: Path, paths: list[str]) -> list[str]:
    cleaned = sorted({str(Path(path).as_posix()).lstrip("/") for path in paths if str(path).strip()})
    if not cleaned:
        raise ObsError("cannot operate on an empty file list")
    root = repo.resolve()
    for relpath in cleaned:
        target = (root / relpath).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ObsError(f"path escapes repository: {relpath}") from exc
        if not target.exists():
            raise ObsError(f"selected file does not exist: {relpath}")
    return cleaned
