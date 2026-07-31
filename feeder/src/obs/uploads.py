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
from .contracts import enqueue_record, provisional_slug, upload_record
from .executables import autoscribe_bin
from .process import run

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



def _call_record(*, identity: str, content: str, extra: dict[str, Any]) -> dict[str, Any]:
    return upload_record(type="call", identity=identity, content=content, extra=extra)


def _upload_and_enqueue(repo: Path, *, calls: list[dict[str, Any]], plan_slug: str) -> str:
    upload = run(
        [autoscribe_bin(), "upload", "calls"],
        cwd=repo,
        input_text=_encode_ndjson(calls).decode("utf-8"),
    )
    manifest = [enqueue_record(call=str(record["identity"]), plan=plan_slug) for record in calls]
    enqueue = run(
        [autoscribe_bin(), "enqueue"],
        cwd=repo,
        input_text=_encode_ndjson(manifest).decode("utf-8"),
    )
    return "\n".join(part for part in (upload.stdout.strip(), enqueue.stdout.strip()) if part)

def _encode_ndjson(records: list[dict[str, Any]]) -> bytes:
    if not records:
        return b""
    text = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    )
    return text.encode("utf-8")


def _resolve_dispatch_item(repo: Path, *, relpath: str, expected_slug: str | None = None) -> dict[str, Any]:
    """Resolve an in-vault Markdown file for dispatch.

    The UI mutates transclusions in place and hands feeder the original vault
    path. Files may live anywhere inside the vault; ``Contents`` is not a
    dispatch boundary. Absolute paths are accepted only when they still resolve
    inside the active vault.
    """
    root = repo.resolve()
    raw_path = str(relpath or "").strip()
    if not raw_path:
        raise ObsError("dispatch item is missing path")

    candidate = Path(raw_path).expanduser()
    absolute = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        normalized = absolute.relative_to(root).as_posix()
    except ValueError as exc:
        raise ObsError(f"dispatch path is outside active vault: {relpath}") from exc

    if absolute.suffix.lower() != ".md":
        raise ObsError(f"dispatch file is not Markdown: {normalized}")
    if not absolute.is_file():
        raise ObsError(f"dispatch file not found: {normalized}")

    source_text = absolute.read_text(encoding="utf-8")
    document = parse_markdown(source_text)
    slug = str(document.frontmatter.get("slug") or "").strip()
    if not slug:
        raise ObsError(f"{normalized}: dispatch file is missing slug")
    if expected_slug and slug != expected_slug:
        raise ObsError(
            f"{normalized}: expected record identity {expected_slug}, found {slug}"
        )

    return {
        "path": normalized,
        "absolute_path": str(absolute),
        "slug": slug,
        "identity": slug,
        "content": document.body,
        "metadata": dict(document.frontmatter),
    }


def dispatch_run(
    repo: Path,
    *,
    manifest_path: Path | None = None,
    dry_run: bool = False,
) -> tuple[list[dict[str, Any]], bytes]:
    """Emit enqueue-ready NDJSON for the active run selection.

    Each call upload contains body text only. Parsed YAML frontmatter is retained
    under ``extra.metadata`` and is never exposed to pipeline transformations.
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
    calls: list[dict[str, Any]] = []
    for item in items:
        item["dispatch_commit"] = commit
        calls.append(_call_record(
            identity=item["identity"],
            content=item["content"],
            extra={
                "filename_hint": Path(item["path"]).name,
                "source_path": item["path"],
                "dispatch_commit": commit,
                "metadata": item["metadata"],
            },
        ))
    pipeline_output = _upload_and_enqueue(repo, calls=calls, plan_slug=plan_slug)
    return items, (pipeline_output + ("\n" if pipeline_output else "")).encode("utf-8")


def dispatch_paths(
    repo: Path,
    *,
    paths: list[str],
    plan_slug: str,
    message: str = "",
    combine_basename: str = "",
    dry_run: bool = False,
    defaults: list[str] | None = None,
    plan_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Dispatch the current explicit Markdown selection.

    Normal dispatch commits the selected files and tags that commit inflight
    after enqueue succeeds. Combined dispatch emits one ordered virtual record
    and deliberately performs no Git commit or tag operation.
    """
    del defaults
    plan = str(plan_slug or "").strip()
    if not plan:
        raise ObsError("dispatch requires plan_slug")
    combined_identity = str(combine_basename or "").strip()
    if combined_identity:
        if Path(combined_identity).name != combined_identity or combined_identity in {".", ".."}:
            raise ObsError("combined record basename must not contain a directory path")
    plan_sync = None

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in paths:
        item = _resolve_dispatch_item(repo, relpath=str(raw or ""))
        if item["path"] in seen:
            continue
        seen.add(item["path"])
        item["plan_slug"] = plan
        items.append(item)

    if not items:
        raise ObsError("selection contains no dispatchable Markdown files")
    if not combined_identity:
        _assert_unique(items, "dispatch")

    from .plans import load_local_plan, sync_plan
    del plan_record
    effective_plan_record = load_local_plan(repo, plan)

    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    user_message = str(message or "").strip()
    subject = user_message or f"DISPATCH {plan}: {stamp}"

    if combined_identity:
        combined_content = "\n\n".join(
            str(item["content"]).rstrip("\n") for item in items
        ) + "\n"
    else:
        combined_content = ""

    if dry_run:
        return {
            "plan_slug": plan,
            "message": subject,
            "count": 1 if combined_identity else len(items),
            "source_count": len(items),
            "combined": bool(combined_identity),
            "record_identity": combined_identity or None,
            "failed_count": 0,
            "items": items,
            "failures": [],
            "pipeline_output": "",
            "commit": None,
            "tag": None,
            "dry_run": True,
            "plan_sync": plan_sync,
        }

    plan_sync = sync_plan(effective_plan_record, cwd=repo)

    calls: list[dict[str, Any]] = []
    if combined_identity:
        # Combined dispatch is a virtual record. It deliberately performs no
        # Git commit or tag operation against the source vault.
        commit = None
        call_identity = provisional_slug(combined_identity)
        calls.append(_call_record(
            identity=call_identity,
            content=combined_content,
            extra={
                "filename_hint": combined_identity,
                "source_paths": [item["path"] for item in items],
                "sources": [
                    {"source_path": item["path"], "metadata": item["metadata"]}
                    for item in items
                ],
            },
        ))
    else:
        # commit_files uses --allow-empty and --only, so an unchanged selection
        # still gets a distinct source commit without including unrelated changes.
        commit = git.commit_files(repo, [item["path"] for item in items], subject)
        for item in items:
            item["dispatch_commit"] = commit
            calls.append(_call_record(
                identity=item["identity"],
                content=item["content"],
                extra={
                    "filename_hint": Path(item["path"]).name,
                    "source_path": item["path"],
                    "dispatch_commit": commit,
                    "metadata": item["metadata"],
                },
            ))

    pipeline_output = _upload_and_enqueue(repo, calls=calls, plan_slug=plan)

    tag_name = None if combined_identity else git.tag_inflight(repo, commit, plan, stamp)
    return {
        "commit": commit,
        "plan_slug": plan,
        "message": subject,
        "count": 1 if combined_identity else len(items),
        "source_count": len(items),
        "combined": bool(combined_identity),
        "record_identity": combined_identity or None,
        "failed_count": 0,
        "items": items,
        "failures": [],
        "pipeline_output": pipeline_output,
        "tag": ({"name": tag_name, "plan_slug": plan, "timestamp": stamp} if tag_name else None),
        "dry_run": False,
        "plan_sync": plan_sync,
    }


def _assert_unique(items: list[dict[str, Any]], label: str) -> None:
    grouped: dict[str, list[str]] = {}
    for item in items:
        identity = str(item.get("identity") or item.get("slug") or "").strip()
        grouped.setdefault(identity, []).append(str(item["path"]))
    duplicates = {identity: paths for identity, paths in grouped.items() if identity and len(paths) > 1}
    if duplicates:
        lines = [f"duplicate {label} record identities:"]
        for identity, paths in duplicates.items():
            lines.append(f"  {identity}")
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
    calls: list[dict[str, Any]] = []
    for path in markdown_paths:
        source_text = git.show_file(repo, commit, path)
        document = parse_markdown(source_text)
        slug = str(document.frontmatter.get("slug") or "").strip()
        if not slug:
            raise ObsError(f"{path}: dispatch file is missing slug")
        record_identity = slug
        item = {
            "path": path,
            "slug": slug,
            "identity": record_identity,
            "content": document.body,
            "metadata": dict(document.frontmatter),
            "dispatch_commit": commit,
            "plan_slug": plan,
        }
        items.append(item)
        calls.append(_call_record(
            identity=record_identity,
            content=document.body,
            extra={
                "filename_hint": Path(path).name,
                "source_path": path,
                "dispatch_commit": commit,
                "metadata": dict(document.frontmatter),
            },
        ))

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

    pipeline_output = _upload_and_enqueue(repo, calls=calls, plan_slug=plan)

    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    tag = git.tag_inflight(repo, commit, plan, stamp)
    return {
        "commit": commit,
        "plan_slug": plan,
        "count": len(items),
        "items": items,
        "pipeline_output": pipeline_output,
        "tag": {"name": tag, "plan_slug": plan, "timestamp": stamp},
        "dry_run": False,
    }
