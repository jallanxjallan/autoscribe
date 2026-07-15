from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

from . import git
from .catalog import instruction_catalog, pipeline_snapshot
from .downloads import writeback, writenew
from .errors import ObsError
from .instruction_upload import upload_instruction
from .plans import delete_plan, list_plans, load_plan, save_plan
from .uploads import dispatch_run
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


def _upload_instruction(repo: Path, request: dict[str, Any]) -> dict[str, Any]:
    return upload_instruction(
        repo,
        source_path=str(request.get("source_path") or ""),
        input_path=Path(str(request.get("input_path") or "")),
        metadata_path=Path(str(request["metadata_path"])) if request.get("metadata_path") else None,
        force=bool(request.get("force")),
        commit=bool(request.get("commit", True)),
    )


def _dispatch(repo: Path, request: dict[str, Any]) -> dict[str, Any]:
    items, output = dispatch_run(repo, manifest_path=Path(request["manifest"]) if request.get("manifest") else None,
                                 dry_run=bool(request.get("dry_run")))
    return {"items": items, "output": output}


def _writeback(repo: Path, request: dict[str, Any]) -> list[dict[str, Any]]:
    return writeback(repo, dry_run=bool(request.get("dry_run")), limit=request.get("limit"))


def _writenew(repo: Path, request: dict[str, Any]) -> list[dict[str, Any]]:
    return writenew(repo, target_dir=str(request.get("target_dir") or "new"),
                    dry_run=bool(request.get("dry_run")), limit=request.get("limit"))



def _plans_list(repo: Path, request: dict[str, Any]) -> list[dict[str, Any]]:
    return list_plans()


def _plan_load(repo: Path, request: dict[str, Any]) -> dict[str, Any]:
    return load_plan(str(request.get("slug") or ""))


def _plan_save(repo: Path, request: dict[str, Any]) -> dict[str, Any]:
    record = request.get("record")
    if not isinstance(record, dict):
        raise ObsError("plan.save requires record object")
    return save_plan(record, cwd=repo)


def _plan_delete(repo: Path, request: dict[str, Any]) -> dict[str, Any]:
    return delete_plan(str(request.get("slug") or ""), cwd=repo)

HANDLERS: dict[str, Handler] = {
    "vault.state": _vault_state,
    "vault.scan": _scan,
    "instructions.catalog": _instructions,
    "pipeline.snapshot": _snapshot,
    "git.commit": _commit,
    "instruction.upload": _upload_instruction,
    "plans.list": _plans_list,
    "plan.load": _plan_load,
    "plan.save": _plan_save,
    "plan.delete": _plan_delete,
    "dispatch.run": _dispatch,
    "writeback": _writeback,
    "writenew": _writenew,
}


def handle(request: dict[str, Any]) -> dict[str, Any]:
    operation = str(request.get("operation") or "").strip()
    if operation not in HANDLERS:
        raise ObsError(f"unknown IPC operation: {operation or '<empty>'}")
    repo = _repo(request)
    result = HANDLERS[operation](repo, request)
    return {"ok": True, "operation": operation, "result": result}


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ObsError("IPC request must be a JSON object")
        print(json.dumps(handle(request), ensure_ascii=False))
        return 0
    except (ObsError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
