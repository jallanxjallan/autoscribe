from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from . import git
from .errors import ObsError
from .manifests import now_iso, read_json, rows, write_json
from .markdown import parse_markdown, slug_prefix
from .pandoc import capture as pandoc_capture
from .state import VaultState
from .vault import Vault

INSTRUCTION_PREFIXES = {"ins", "gbl", "cxt", "spc"}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _emit_pandoc(repo: Path, relpath: str, defaults: list[str], metadata: dict[str, Any]) -> str:
    output = pandoc_capture(repo=repo, input_path=relpath, defaults=defaults, metadata=metadata)
    if output and not output.endswith("\n"):
        output += "\n"
    return output


def upload_instructions(repo: Path, *, force: bool = False, dry_run: bool = False,
                        defaults: list[str] | None = None) -> tuple[list[dict[str, Any]], str]:
    vault = Vault(repo)
    candidates = {path.relative_to(repo).as_posix() for path in vault.markdown_paths()}
    if not force:
        candidates &= set(git.dirty_files(repo))
    items: list[dict[str, Any]] = []
    for relpath in sorted(candidates):
        path = repo / relpath
        document = parse_markdown(path.read_text(encoding="utf-8"))
        slug = str(document.frontmatter.get("slug") or "").strip()
        if slug_prefix(slug) not in INSTRUCTION_PREFIXES:
            continue
        items.append({
            "slug": slug,
            "path": relpath,
            "prefix": slug_prefix(slug),
            "previous_commit": git.last_commit(repo, relpath),
            "content_sha256": _sha256(document.body.strip()),
        })
    _assert_unique(items, "instruction")
    if dry_run or not items:
        return items, ""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    commit = git.commit_files(repo, [item["path"] for item in items], f"UPLOAD instructions: {stamp}")
    uploaded_at = now_iso()
    output = ""
    for order, item in enumerate(items, 1):
        metadata = {
            "slug": item["slug"], "record_identity": item["slug"],
            "record_type": "instruction", "control_prefix": item["prefix"],
            "source": {
                "origin": "obsidian.upload-instructions", "vault_root": str(repo),
                "path": item["path"], "filename_hint": Path(item["path"]).name,
                "previous_commit": item["previous_commit"], "upload_commit": commit,
                "uploaded_at": uploaded_at, "content_sha256": item["content_sha256"],
                "selection_mode": "force-all-matching-prefix" if force else "dirty-matching-prefix",
                "selection_order": order,
            },
        }
        output += _emit_pandoc(repo, item["path"], defaults or ["upload_control"], metadata)
    return items, output


def dispatch_run(repo: Path, *, manifest_path: Path | None = None, dry_run: bool = False,
                 defaults: list[str] | None = None) -> tuple[list[dict[str, Any]], str]:
    vault = Vault(repo)
    manifest_path = manifest_path or VaultState.for_vault(repo).current_run
    manifest = read_json(manifest_path)
    manifest_root = manifest.get("vault_root") or (manifest.get("vault") or {}).get("root")
    if manifest_root and Path(manifest_root).resolve() != repo.resolve():
        raise ObsError(f"run manifest belongs to a different vault: {manifest_root}")
    slug_map = vault.slug_map()
    calls: list[dict[str, Any]] = []
    for index, raw in enumerate(rows(manifest), 1):
        if str(raw.get("upload_status") or "pending") != "pending":
            continue
        prompt_slug = raw.get("prompt_slug") or raw.get("call_slug") or raw.get("record_identity") or raw.get("slug")
        plan_slug = raw.get("plan_slug") or raw.get("job_slug") or raw.get("plan") or manifest.get("plan_slug")
        if not prompt_slug or not plan_slug:
            raise ObsError(f"manifest row {index}: missing prompt_slug or plan_slug")
        record = slug_map.get(str(prompt_slug))
        if not record:
            raise ObsError(f"{prompt_slug}: prompt slug not found in active vault")
        calls.append({"index": index, "raw": raw, "prompt_slug": str(prompt_slug),
                      "call_slug": str(raw.get("call_slug") or prompt_slug),
                      "plan_slug": str(plan_slug), "path": record.path})
    if dry_run or not calls:
        return calls, ""
    uploaded_at = now_iso()
    output = ""
    manifest_rows = rows(manifest)
    for call in calls:
        try:
            output += _emit_pandoc(repo, call["path"], defaults or ["upload_prompt"],
                                   {"record_plan": call["plan_slug"]})
            manifest_rows[call["index"] - 1].update({"upload_status": "uploaded", "uploaded_at": uploaded_at,
                                                       "upload_error": ""})
        except Exception as exc:
            manifest_rows[call["index"] - 1].update({"upload_status": "error", "upload_error": str(exc)})
            write_json(manifest_path, manifest)
            raise
    write_json(manifest_path, manifest)
    return calls, output


def _assert_unique(items: list[dict[str, Any]], label: str) -> None:
    grouped: dict[str, list[str]] = {}
    for item in items:
        grouped.setdefault(item["slug"], []).append(str(item["path"]))
    duplicates = {slug: paths for slug, paths in grouped.items() if len(paths) > 1}
    if duplicates:
        lines = [f"duplicate {label} slugs:"]
        for slug, paths in duplicates.items():
            lines.append(f"  {slug}")
            lines.extend(f"    - {path}" for path in paths)
        raise ObsError("\n".join(lines))
