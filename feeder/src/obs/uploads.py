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



def _dispatch_record(*, slug: str, plan_slug: str, content: str) -> dict[str, str]:
    return {
        "record_identity": slug,
        "record_type": "content",
        "record_plan": plan_slug,
        "record_content": content,
    }


def _encode_ndjson(records: list[dict[str, str]]) -> bytes:
    if not records:
        return b""
    text = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    )
    return text.encode("utf-8")


def _resolve_dispatch_item(repo: Path, *, relpath: str, expected_slug: str | None = None) -> dict[str, str]:
    root = repo.resolve()
    normalized_input = str(relpath or "").replace("\\", "/").lstrip("./")
    if not normalized_input:
        raise ObsError("dispatch item is missing path")

    absolute = (root / normalized_input).resolve()
    try:
        normalized = absolute.relative_to(root).as_posix()
    except ValueError as exc:
        raise ObsError(f"dispatch path is outside active vault: {relpath}") from exc

    if absolute.suffix.lower() != ".md":
        raise ObsError(f"dispatch file is not Markdown: {normalized}")
    if not absolute.is_file():
        raise ObsError(f"dispatch file not found: {normalized}")

    content = absolute.read_text(encoding="utf-8")
    document = parse_markdown(content)
    slug = str(document.frontmatter.get("slug") or "").strip()
    if not slug:
        raise ObsError(f"{normalized}: missing slug")
    if expected_slug and slug != expected_slug:
        raise ObsError(f"{normalized}: expected slug {expected_slug}, found {slug}")

    return {
        "path": normalized,
        "absolute_path": str(absolute),
        "slug": slug,
        "record_content": content,
    }


def dispatch_run(
    repo: Path,
    *,
    manifest_path: Path | None = None,
    dry_run: bool = False,
) -> tuple[list[dict[str, Any]], bytes]:
    """Emit enqueue-ready NDJSON for the active run selection.

    Each row contains only ``record_identity``, ``record_type``,
    ``record_plan``, and ``record_content``. ``record_content`` is the entire
    Markdown source file, including YAML frontmatter and body.
    """
    manifest_path = manifest_path or VaultState.for_vault(repo).current_run
    manifest = read_json(manifest_path)
    manifest_root = manifest.get("vault_root") or (manifest.get("vault") or {}).get("root")
    if manifest_root and Path(manifest_root).resolve() != repo.resolve():
        raise ObsError(f"run manifest belongs to a different vault: {manifest_root}")

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(rows(manifest), 1):
        if str(raw.get("upload_status") or "pending") != "pending":
            continue

        plan_slug = str(
            raw.get("plan_slug")
            or raw.get("job_slug")
            or raw.get("plan")
            or manifest.get("plan_slug")
            or ""
        ).strip()
        if not plan_slug:
            raise ObsError(f"manifest row {index}: missing plan_slug")

        expected_slug = str(
            raw.get("prompt_slug")
            or raw.get("call_slug")
            or raw.get("record_identity")
            or raw.get("slug")
            or ""
        ).strip() or None
        item = _resolve_dispatch_item(
            repo,
            relpath=str(raw.get("path") or ""),
            expected_slug=expected_slug,
        )
        if item["path"] in seen:
            continue
        seen.add(item["path"])
        item.update({"index": index, "plan_slug": plan_slug})
        items.append(item)

    if not items:
        raise ObsError("current selection contains no dispatchable Markdown files")

    plan_slugs = {item["plan_slug"] for item in items}
    if len(plan_slugs) != 1:
        raise ObsError("dispatch run must use exactly one plan slug")
    plan_slug = next(iter(plan_slugs))

    if dry_run:
        return items, b""

    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    commit = git.commit_files(repo, [item["path"] for item in items], f"{plan_slug} {stamp}")
    records: list[dict[str, str]] = []
    for item in items:
        item["dispatch_commit"] = commit
        records.append(
            _dispatch_record(
                slug=item["slug"],
                plan_slug=plan_slug,
                content=item["record_content"],
            )
        )
    return items, _encode_ndjson(records)


def dispatch_paths(
    repo: Path,
    *,
    paths: list[str],
    plan_slug: str,
    dry_run: bool = False,
    defaults: list[str] | None = None,
) -> dict[str, Any]:
    """Commit explicit Markdown paths and send their canonical NDJSON to enqueue."""
    del defaults
    plan_slug = str(plan_slug or "").strip()
    if not plan_slug:
        raise ObsError("dispatch requires plan_slug")

    items: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in paths:
        item = _resolve_dispatch_item(repo, relpath=str(raw or ""))
        if item["path"] in seen:
            continue
        seen.add(item["path"])
        item["plan_slug"] = plan_slug
        items.append(item)

    if not items and failures:
        return {
            "plan_slug": plan_slug,
            "count": 0,
            "failed_count": len(failures),
            "items": [],
            "failures": failures,
            "pipeline_output": "",
            "dry_run": dry_run,
        }
    if not items:
        raise ObsError("selection contains no dispatchable Markdown files")
    if dry_run:
        return {
            "plan_slug": plan_slug,
            "count": len(items),
            "items": items,
            "failed_count": len(failures),
            "failures": failures,
            "pipeline_output": "",
            "dry_run": True,
        }

    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    commit = git.commit_files(repo, [item["path"] for item in items], f"{plan_slug} {stamp}")
    records = []
    for item in items:
        item["dispatch_commit"] = commit
        records.append(
            _dispatch_record(
                slug=item["slug"],
                plan_slug=plan_slug,
                content=item["record_content"],
            )
        )

    import os
    import subprocess
    from .executables import autoscribe_bin

    command = [autoscribe_bin(), "enqueue"]
    result = subprocess.run(
        command,
        cwd=repo,
        env=os.environ.copy(),
        input=_encode_ndjson(records),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or f"exit status {result.returncode}".encode()).decode(
            "utf-8", errors="replace"
        ).strip()
        raise ObsError(f"{' '.join(command)} failed: {detail}")

    return {
        "plan_slug": plan_slug,
        "count": len(items),
        "failed_count": len(failures),
        "items": items,
        "failures": failures,
        "pipeline_output": result.stdout.decode("utf-8", errors="replace").strip(),
        "dry_run": False,
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


def dispatch_commit(
    repo: Path,
    *,
    commit_hash: str,
    plan_slug: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Dispatch the Markdown members of an existing user commit.

    Content is read from the selected commit, not from the working tree. The
    commit receives an annotated inflight tag only after enqueue succeeds.
    """
    commit = str(commit_hash or "").strip()
    plan = str(plan_slug or "").strip()
    if not commit:
        raise ObsError("dispatch requires commit_hash")
    if not plan:
        raise ObsError("dispatch requires plan_slug")
    if git.is_inflight(repo, commit):
        raise ObsError(f"commit is already tagged inflight: {commit[:8]}")

    paths = git.files_in_commit(repo, commit)
    markdown_paths = [path for path in paths if Path(path).suffix.lower() == ".md"]
    if not markdown_paths:
        raise ObsError("selected commit contains no Markdown files")

    items: list[dict[str, Any]] = []
    records: list[dict[str, str]] = []
    for path in markdown_paths:
        content = git.show_file(repo, commit, path)
        document = parse_markdown(content)
        slug = str(document.frontmatter.get("slug") or "").strip()
        if not slug:
            raise ObsError(f"{path}: missing slug in selected commit")
        item = {
            "path": path,
            "slug": slug,
            "record_content": content,
            "dispatch_commit": commit,
            "plan_slug": plan,
        }
        items.append(item)
        records.append(_dispatch_record(slug=slug, plan_slug=plan, content=content))

    _assert_unique(items, "dispatch")
    if dry_run:
        return {
            "commit": commit,
            "plan_slug": plan,
            "count": len(items),
            "items": items,
            "pipeline_output": "",
            "tag": None,
            "dry_run": True,
        }

    import os
    import subprocess
    from .executables import autoscribe_bin

    command = [autoscribe_bin(), "enqueue"]
    result = subprocess.run(
        command,
        cwd=repo,
        env=os.environ.copy(),
        input=_encode_ndjson(records),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or f"exit status {result.returncode}".encode()).decode(
            "utf-8", errors="replace"
        ).strip()
        raise ObsError(f"{' '.join(command)} failed: {detail}")

    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    tag = git.tag_inflight(repo, commit, plan, stamp)
    return {
        "commit": commit,
        "plan_slug": plan,
        "count": len(items),
        "items": items,
        "pipeline_output": result.stdout.decode("utf-8", errors="replace").strip(),
        "tag": {"name": tag, "plan_slug": plan, "timestamp": stamp},
        "dry_run": False,
    }
