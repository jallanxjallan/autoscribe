from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


def request() -> dict[str, Any]:
    value = json.load(sys.stdin)
    if not isinstance(value, dict):
        raise ValueError("file-state request must be a JSON object")
    return value


def run_git(root: Path, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "git command failed").strip())
    return result


def repo_root(vault_root: Path) -> Path:
    result = run_git(vault_root, ["rev-parse", "--show-toplevel"])
    return Path(result.stdout.strip()).resolve()


def rel_to_repo(repo: Path, vault: Path, vault_relative: str) -> str:
    absolute = (vault / vault_relative).resolve()
    try:
        return absolute.relative_to(repo).as_posix()
    except ValueError as exc:
        raise ValueError(f"path is outside repository: {vault_relative}") from exc


def parse_frontmatter(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {}
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    raw = text[4:end]
    if yaml is not None:
        try:
            value = yaml.safe_load(raw) or {}
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}
    result: dict[str, Any] = {}
    for line in raw.splitlines():
        if ":" not in line or line[:1].isspace():
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip().strip('"\'')
    return result


def status_map(repo: Path) -> dict[str, tuple[str, str]]:
    result = run_git(repo, ["status", "--porcelain=v1", "-z", "--untracked-files=all"])
    entries = result.stdout.split("\0")
    statuses: dict[str, tuple[str, str]] = {}
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        code = entry[:2]
        path = entry[3:]
        if code[0] in "RC" and index < len(entries):
            path = entries[index]
            index += 1
        statuses[path] = (code[0], code[1])
    return statuses


def state_label(index_state: str, worktree_state: str) -> str:
    code = f"{index_state}{worktree_state}"
    if "U" in code or code in {"AA", "DD"}:
        return "conflicted"
    if code == "??":
        return "new"
    if "D" in code:
        return "deleted"
    if "R" in code or "C" in code:
        return "renamed"
    if index_state not in {" ", "?"} and worktree_state not in {" ", "?"}:
        return "staged + modified"
    if index_state not in {" ", "?"}:
        return "staged"
    if worktree_state not in {" ", "?"}:
        return "modified"
    return "clean"


def latest_commit(repo: Path, repo_path: str) -> dict[str, Any] | None:
    result = run_git(
        repo,
        ["log", "-1", "--format=%H%x1f%s%x1f%ct", "--", repo_path],
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    commit_hash, subject, timestamp = (result.stdout.strip().split("\x1f") + ["", ""])[:3]
    return {"hash": commit_hash, "subject": subject, "timestamp": int(timestamp or 0)}


def list_files(vault: Path, sort: str) -> list[dict[str, Any]]:
    repo = repo_root(vault)
    prefix = vault.relative_to(repo).as_posix()
    patterns = [f"{prefix}/**/*.md"] if prefix != "." else ["**/*.md"]
    tracked = run_git(repo, ["ls-files", "--cached", "--others", "--exclude-standard", "--", *patterns])
    statuses = status_map(repo)
    files: list[dict[str, Any]] = []
    for repo_path in sorted(set(filter(None, tracked.stdout.splitlines()))):
        try:
            rel = Path(repo_path).relative_to(prefix).as_posix() if prefix != "." else Path(repo_path).as_posix()
        except ValueError:
            continue
        parts = Path(rel).parts
        if not rel.endswith(".md") or any(part.startswith("_") for part in parts[:-1]):
            continue
        absolute = vault / rel
        index_state, worktree_state = statuses.get(repo_path, (" ", " "))
        meta = parse_frontmatter(absolute) if absolute.exists() else {}
        stat = absolute.stat() if absolute.exists() else None
        title = str(meta.get("title") or Path(rel).stem)
        files.append({
            "path": rel,
            "title": title,
            "slug": str(meta.get("slug") or ""),
            "record": str(meta.get("record") or meta.get("type") or ""),
            "component": str(meta.get("component") or meta.get("class") or ""),
            "stage": str(meta.get("stage") or ""),
            "status": str(meta.get("status") or ""),
            "action": str(meta.get("action") or ""),
            "scope": meta.get("scope") or "",
            "position": str(meta.get("position") or ""),
            "mtime": int(stat.st_mtime) if stat else 0,
            "worktree": {
                "label": state_label(index_state, worktree_state),
                "index": index_state,
                "worktree": worktree_state,
            },
            "user_commit": latest_commit(repo, repo_path),
        })
    if sort == "mtime_desc":
        files.sort(key=lambda item: (-int(item["mtime"]), item["title"].lower()))
    elif sort == "user_commit_desc":
        files.sort(key=lambda item: (-int((item["user_commit"] or {}).get("timestamp", 0)), item["title"].lower()))
    else:
        files.sort(key=lambda item: (item["title"].lower(), item["path"].lower()))
    return files


def commit_files(vault: Path, paths: list[str], message: str, amend: bool) -> dict[str, Any]:
    if not paths:
        raise ValueError("no files selected")
    if not amend and not message.strip():
        raise ValueError("commit message is required")
    repo = repo_root(vault)
    repo_paths = [rel_to_repo(repo, vault, path) for path in paths]
    run_git(repo, ["add", "--", *repo_paths])
    staged = run_git(repo, ["diff", "--cached", "--name-only", "--", *repo_paths]).stdout.splitlines()
    if not staged:
        raise ValueError("selected files contain no staged changes")
    args = ["commit"]
    if amend:
        args.extend(["--amend", "--no-edit"] if not message.strip() else ["--amend", "-m", message.strip()])
    else:
        args.extend(["-m", message.strip()])
    args.extend(["--", *repo_paths])
    run_git(repo, args)
    commit_hash = run_git(repo, ["rev-parse", "HEAD"]).stdout.strip()
    return {"commit": commit_hash, "files": staged}


def main() -> int:
    try:
        data = request()
        vault = Path(str(data.get("vault_root") or "")).expanduser().resolve()
        if not vault.is_dir():
            raise ValueError(f"invalid vault root: {vault}")
        operation = str(data.get("operation") or "refresh")
        if operation == "refresh":
            result = {"files": list_files(vault, str(data.get("sort") or "title_asc"))}
        elif operation == "commit":
            paths = data.get("paths")
            if not isinstance(paths, list):
                raise ValueError("commit request requires paths list")
            result = commit_files(vault, [str(path) for path in paths], str(data.get("message") or ""), bool(data.get("amend")))
        else:
            raise ValueError(f"unknown file-state operation: {operation}")
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
