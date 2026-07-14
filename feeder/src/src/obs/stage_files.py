from __future__ import annotations

from pathlib import Path
from typing import Any

from . import git
from .errors import ObsError
from .vault import Vault

SORTS = {"title_asc", "mtime_desc", "user_commit_desc"}


def refresh(
    repo: Path,
    *,
    stages: list[str] | None = None,
    statuses: list[str] | None = None,
    sort: str = "title_asc",
) -> list[dict[str, Any]]:
    if sort not in SORTS:
        raise ObsError(f"unknown Stage Files sort: {sort}")
    stage_filter = {value.strip() for value in (stages or []) if value.strip()}
    status_filter = {value.strip() for value in (statuses or []) if value.strip()}
    states = git.status_map(repo)
    events = git.dispatch_events(repo)
    rows: list[dict[str, Any]] = []
    for record in Vault(repo).records():
        stage = str(record.frontmatter.get("stage") or "").strip()
        status = str(record.frontmatter.get("status") or "").strip()
        if stage_filter and stage not in stage_filter:
            continue
        if status_filter and status not in status_filter:
            continue
        path = repo / record.path
        latest = git.latest_commit(repo, record.path)
        user = git.latest_user_commit(repo, record.path)
        worktree = git.worktree_state(repo, record.path, states)
        dispatch = git.dispatch_state(repo, record.path, latest, events)
        if worktree.label != "clean" and dispatch["state"] == "in-flight":
            dispatch = {**dispatch, "state": "conflict", "reason": f"worktree_{worktree.label}"}
        rows.append({
            "slug": record.slug,
            "path": record.path,
            "title": str(record.frontmatter.get("title") or path.stem),
            "stage": stage,
            "status": status,
            "mtime": int(path.stat().st_mtime),
            "worktree": worktree.as_dict(),
            "user_commit": user.as_dict() if user else None,
            "latest_commit": latest.as_dict() if latest else None,
            "dispatch": dispatch,
        })
    if sort == "title_asc":
        rows.sort(key=lambda row: (row["title"].casefold(), row["path"].casefold()))
    elif sort == "mtime_desc":
        rows.sort(key=lambda row: (-row["mtime"], row["title"].casefold()))
    else:
        rows.sort(key=lambda row: (
            -(row["user_commit"] or {}).get("timestamp", 0),
            (row["user_commit"] or {}).get("hash", ""),
            row["title"].casefold(),
        ))
    return rows
