from __future__ import annotations

from pathlib import Path
from typing import Any

from . import git
from .errors import ObsError
from .stage_files import refresh
from .vault import Vault


def handle(repo: Path, request: dict[str, Any]) -> dict[str, Any]:
    action = str(request.get("action") or "").strip()
    if action == "stage_files.refresh":
        filters = request.get("filters") or {}
        files = refresh(
            repo,
            stages=_strings(filters.get("stage")),
            statuses=_strings(filters.get("status")),
            sort=str(request.get("sort") or "title_asc"),
        )
        return {"ok": True, "files": files}
    if action == "stage_files.commit":
        paths = _indexed_paths(repo, _strings(request.get("paths")))
        commit = git.commit_files(
            repo, paths, str(request.get("message") or ""), amend=bool(request.get("amend", False))
        )
        info = git.latest_commit(repo, paths[0])
        return {"ok": True, "commit": commit, "subject": info.subject if info else "", "files": paths}
    if action == "dispatch.create":
        paths = _indexed_paths(repo, _strings(request.get("paths")))
        user_commit = str(request.get("user_commit") or "").strip()
        plan = str(request.get("plan") or "").strip()
        if not user_commit:
            raise ObsError("user_commit is required")
        if not plan:
            raise ObsError("plan is required")
        commit = git.create_dispatch_commit(repo, paths, user_commit, plan)
        return {"ok": True, "dispatch_commit": commit, "user_commit": user_commit, "plan": plan, "files": paths}
    raise ObsError(f"unknown IPC action: {action or '<empty>'}")


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ObsError("expected a JSON array")
    return [str(item) for item in value]


def _indexed_paths(repo: Path, requested: list[str]) -> list[str]:
    indexed = {record.path for record in Vault(repo).records()}
    missing = sorted(set(requested) - indexed)
    if missing:
        raise ObsError("selected paths are not in the current rg index:\n" + "\n".join(f"  {path}" for path in missing))
    return sorted(set(requested))
