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
from .pandoc import capture as pandoc_capture, emit as pandoc_emit
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


def dispatch_run(
    repo: Path,
    *,
    manifest_path: Path | None = None,
    dry_run: bool = False,
) -> tuple[list[dict[str, Any]], bytes]:
    """Resolve a run into NUL-delimited Pandoc argument pairs.

    The CLI stream is consumed by ``xargs -0 -r -n 2 pandoc``. Each file adds
    one ``record_plan`` metadata option and one absolute Markdown filename.
    """
    manifest_path = manifest_path or VaultState.for_vault(repo).current_run
    manifest = read_json(manifest_path)
    manifest_root = manifest.get("vault_root") or (manifest.get("vault") or {}).get("root")
    if manifest_root and Path(manifest_root).resolve() != repo.resolve():
        raise ObsError(f"run manifest belongs to a different vault: {manifest_root}")

    root = repo.resolve()
    calls: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(rows(manifest), 1):
        if str(raw.get("upload_status") or "pending") != "pending":
            continue
        plan_slug = raw.get("plan_slug") or raw.get("job_slug") or raw.get("plan") or manifest.get("plan_slug")
        relpath = str(raw.get("path") or "").replace("\\", "/").lstrip("./")
        prompt_slug = raw.get("prompt_slug") or raw.get("call_slug") or raw.get("record_identity") or raw.get("slug")
        if not relpath or not plan_slug:
            raise ObsError(f"manifest row {index}: missing path or plan_slug")

        absolute = (root / relpath).resolve()
        try:
            normalized = absolute.relative_to(root).as_posix()
        except ValueError as exc:
            raise ObsError(f"manifest row {index}: path is outside active vault: {relpath}") from exc
        if normalized in seen:
            continue
        if absolute.suffix.lower() != ".md":
            raise ObsError(f"manifest row {index}: selected file is not Markdown: {normalized}")
        if not absolute.is_file():
            raise ObsError(f"manifest row {index}: selected file not found: {normalized}")

        seen.add(normalized)
        calls.append({
            "index": index,
            "prompt_slug": str(prompt_slug or ""),
            "plan_slug": str(plan_slug),
            "path": normalized,
            "absolute_path": str(absolute),
        })

    if not calls:
        raise ObsError("current selection contains no dispatchable Markdown files")

    plan_slugs = {call["plan_slug"] for call in calls}
    if len(plan_slugs) != 1:
        raise ObsError("dispatch run must use exactly one plan slug")
    plan_slug = next(iter(plan_slugs))

    if not dry_run:
        stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
        commit = git.commit_files(
            repo,
            [call["path"] for call in calls],
            f"{plan_slug} {stamp}",
        )
        for call in calls:
            call["dispatch_commit"] = commit

    output = bytearray()
    for call in calls:
        output.extend(f"--metadata=record_plan:{plan_slug}".encode("utf-8"))
        output.append(0)
        output.extend(call["absolute_path"].encode("utf-8"))
        output.append(0)
    return calls, bytes(output)


def dispatch_paths(
    repo: Path,
    *,
    paths: list[str],
    plan_slug: str,
    dry_run: bool = False,
    defaults: list[str] | None = None,
) -> dict[str, Any]:
    """Render explicit Markdown paths and enqueue them under one uploaded plan."""
    plan_slug = str(plan_slug or "").strip()
    if not plan_slug:
        raise ObsError("dispatch requires plan_slug")
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        relpath = str(raw or "").replace("\\", "/").lstrip("./")
        if not relpath or relpath in seen:
            continue
        candidate = (repo / relpath).resolve()
        try:
            candidate.relative_to(repo.resolve())
        except ValueError as exc:
            raise ObsError(f"dispatch path is outside active vault: {raw}") from exc
        if candidate.suffix.lower() != ".md":
            continue
        if not candidate.is_file():
            raise ObsError(f"dispatch file not found: {relpath}")
        document = parse_markdown(candidate.read_text(encoding="utf-8"))
        slug = str(document.frontmatter.get("slug") or "").strip()
        if not slug:
            raise ObsError(f"{relpath}: missing slug")
        seen.add(relpath)
        normalized.append(relpath)
    if not normalized:
        raise ObsError("selected commit contains no dispatchable Markdown files")

    items: list[dict[str, Any]] = []
    for relpath in normalized:
        document = parse_markdown((repo / relpath).read_text(encoding="utf-8"))
        slug = str(document.frontmatter.get("slug") or "").strip()
        items.append({"path": relpath, "slug": slug, "plan_slug": plan_slug})

    pipeline_output = ""
    if not dry_run:
        import os
        import subprocess

        from .executables import autoscribe_bin

        command = [autoscribe_bin(), "enqueue"]
        enqueue = subprocess.Popen(
            command,
            cwd=repo,
            env=os.environ.copy(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert enqueue.stdin is not None
        assert enqueue.stdout is not None
        assert enqueue.stderr is not None
        try:
            for item in items:
                pandoc_emit(
                    repo=repo,
                    input_path=item["path"],
                    defaults=defaults or ["upload_prompt"],
                    metadata={"record_plan": plan_slug},
                    stdout=enqueue.stdin,
                )
            enqueue.stdin.close()
            pipeline_stdout = enqueue.stdout.read()
            pipeline_stderr = enqueue.stderr.read()
            returncode = enqueue.wait()
        except Exception:
            enqueue.kill()
            enqueue.wait()
            raise
        if returncode != 0:
            detail = (pipeline_stderr or pipeline_stdout or f"exit status {returncode}").strip()
            raise ObsError(f"{' '.join(command)} failed: {detail}")
        pipeline_output = pipeline_stdout.strip()
    return {
        "plan_slug": plan_slug,
        "count": len(items),
        "items": items,
        "pipeline_output": pipeline_output,
        "dry_run": dry_run,
    }


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
