from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

from . import git
from .catalog import instruction_catalog, pipeline_snapshot
from .retrieval import retrieve_results
from .errors import ObsError
from .git_selection import commit_selection, resolve_selection
from .plans import delete_plan, list_plans, load_plan, save_plan
from .uploads import dispatch_paths, dispatch_run
from .vault import Vault

Handler = Callable[[Path, dict[str, Any]], Any]


def _repo(request: dict[str, Any]) -> Path:
    raw = request.get("vault") or request.get("repo")
    return Path(raw).expanduser().resolve() if raw else git.root(Path.cwd())


def _vault_state(repo: Path, request: dict[str, Any]) -> dict[str, Any]:
    return {"vault_root": str(repo), "head": git.head(repo), "dirty": git.status_records(repo)}


def _scan(repo: Path, request: dict[str, Any]) -> list[dict[str, Any]]:
    records = Vault(repo).records(public_only=bool(request.get("public")))
    return [record.__dict__ for record in records]


def _instructions(repo: Path, request: dict[str, Any]) -> list[dict[str, Any]]:
    roots = request.get("roots")
    library = request.get("library_vault") or os.environ.get("AUTOSCRIBE_LIBRARY_VAULT")
    return instruction_catalog(repo, roots=roots, library_vault=library, include_pipeline=bool(request.get("include_pipeline", True)))


def _snapshot(repo: Path, request: dict[str, Any]) -> dict[str, Any]:
    kind = str(request.get("kind") or "registry")
    return pipeline_snapshot(kind)


def _commit(repo: Path, request: dict[str, Any]) -> dict[str, Any]:
    paths = [str(value) for value in request.get("paths") or []]
    message = str(request.get("message") or "").strip()
    if not message:
        raise ObsError("git.commit requires message")
    return {"commit": git.commit_files(repo, paths, message, str(request.get("body") or "")), "paths": paths}



def _resolve_selection(repo: Path, request: dict[str, Any]) -> dict[str, Any]:
    items = request.get("items")
    if not isinstance(items, list):
        raise ObsError("git.resolve_selection requires items list")
    return resolve_selection(repo, items)


def _commit_selection(repo: Path, request: dict[str, Any]) -> dict[str, Any]:
    items = request.get("items")
    if not isinstance(items, list):
        raise ObsError("git.commit_selection requires items list")
    return commit_selection(repo, items, str(request.get("message") or ""))

def _dispatch(repo: Path, request: dict[str, Any]) -> dict[str, Any]:
    paths = request.get("paths")
    if not isinstance(paths, list):
        raise ObsError("dispatch.run requires paths list")
    return dispatch_paths(
        repo,
        paths=[str(path) for path in paths],
        plan_slug=str(request.get("plan_slug") or ""),
        message=str(request.get("message") or ""),
        combine_basename=str(request.get("combine_basename") or ""),
        dry_run=bool(request.get("dry_run")),
        plan_record=request.get("plan_record"),
    )



def _retrieve_results(repo: Path, request: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    branch = str(request.get("branch") or "").strip() or None
    return retrieve_results(
        repo,
        branch=branch,
        dry_run=bool(request.get("dry_run")),
        force=bool(request.get("force")),
    )



def _plans_list(repo: Path, request: dict[str, Any]) -> list[dict[str, Any]]:
    return list_plans()


def _plan_load(repo: Path, request: dict[str, Any]) -> dict[str, Any]:
    return load_plan(str(request.get("slug") or ""))


def _plan_save(repo: Path, request: dict[str, Any]) -> dict[str, Any]:
    record = request.get("record")
    if not isinstance(record, dict):
        raise ObsError("plan.save requires record object")
    instruction_sets = request.get("instruction_sets")
    if instruction_sets is not None and not isinstance(instruction_sets, list):
        raise ObsError("plan.save instruction_sets must be a list")
    return save_plan(
        record,
        cwd=repo,
        instruction_sets=instruction_sets or [],
        publication_ulid=str(request.get("publication_ulid") or ""),
    )


def _plan_delete(repo: Path, request: dict[str, Any]) -> dict[str, Any]:
    return delete_plan(str(request.get("slug") or ""), cwd=repo)

HANDLERS: dict[str, Handler] = {
    "vault.state": _vault_state,
    "vault.scan": _scan,
    "instructions.catalog": _instructions,
    "pipeline.snapshot": _snapshot,
    "git.commit": _commit,
    "git.resolve_selection": _resolve_selection,
    "git.commit_selection": _commit_selection,
    "plans.list": _plans_list,
    "plan.load": _plan_load,
    "plan.save": _plan_save,
    "plan.delete": _plan_delete,
    "dispatch.run": _dispatch,
    "results.retrieve": _retrieve_results,
}


def handle(request: dict[str, Any], *, repo: Path | None = None) -> dict[str, Any]:
    operation = str(request.get("operation") or "").strip()
    if operation not in HANDLERS:
        raise ObsError(f"unknown IPC operation: {operation or '<empty>'}")
    resolved_repo = repo if repo is not None else _repo(request)
    result = HANDLERS[operation](resolved_repo, request)
    return {"ok": True, "operation": operation, "result": result}


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ObsError("IPC request must be a JSON object")
        print(json.dumps(handle(request), ensure_ascii=False))
        return 0
    except Exception as exc:
        # stdout must remain valid JSON for the Obsidian caller. Preserve the
        # traceback on stderr for diagnosis while returning a structured error.
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"ok": False, "error": str(exc), "error_type": type(exc).__name__}, ensure_ascii=False))
        return 1
