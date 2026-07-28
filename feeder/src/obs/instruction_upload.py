from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from . import git
from .catalog import pipeline_snapshot
from .errors import ObsError
from .executables import autoscribe_bin
from .markdown import parse_markdown
from .process import run


def _inside(root: Path, path: Path) -> bool:
    root = root.resolve()
    path = path.resolve()
    return path == root or root in path.parents


def _instruction_hashes(snapshot: dict[str, Any]) -> dict[str, str]:
    values = snapshot.get("registries", {}).get("instructions", {})
    if not isinstance(values, dict):
        return {}
    result: dict[str, str] = {}
    for slug, record in values.items():
        if isinstance(record, dict):
            value = str(record.get("content_sha256") or "").strip()
            if value:
                result[str(slug)] = value
    return result




def _upload_envelope(record: dict[str, Any]) -> dict[str, Any]:
    """Return the strict instruction upload envelope."""
    record_type = str(record.get("record_type") or "instruction").strip()
    record_identity = str(record.get("record_identity") or record.get("slug") or "").strip()
    if record_type != "instruction":
        raise ObsError(f"expected instruction record_type, got: {record_type or '<empty>'}")
    if not record_identity:
        raise ObsError("instruction record missing record_identity")

    raw_payload = record.get("payload")
    if not isinstance(raw_payload, dict):
        raise ObsError(f"{record_identity}: instruction payload must be an object")
    content = raw_payload.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ObsError(f"{record_identity}: instruction payload requires non-empty content")

    return {
        "record_type": "instruction",
        "record_identity": record_identity,
        "payload": {"content": content},
    }


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _render_body_record(repo: Path, *, slug: str, source: Path, source_path: str) -> tuple[dict[str, Any], str]:
    """Build the simple upload record directly from the Markdown body.

    Instruction uploads are not document conversions. Frontmatter is routing
    metadata and is excluded; the body is sent unchanged as ``payload.content``.
    """
    del repo, source_path
    document = parse_markdown(source.read_text(encoding="utf-8"))
    actual_slug = str(document.frontmatter.get("slug") or "").strip()
    if actual_slug != slug:
        raise ObsError(f"{source}: expected slug {slug}, found {actual_slug or '<empty>'}")
    content = document.body
    if not content.strip():
        raise ObsError(f"{source}: instruction body is empty")

    record = {
        "record_type": "instruction",
        "record_identity": slug,
        "payload": {"content": content},
    }
    return record, _content_hash(content)


def _instruction_remote_state(snapshot: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    values = snapshot.get("registries", {}).get("instructions", {})
    if not isinstance(values, dict):
        return {}, {}
    hashes: dict[str, str] = {}
    contents: dict[str, str] = {}
    for key, record in values.items():
        if not isinstance(record, dict):
            continue
        slug = str(record.get("record_identity") or record.get("slug") or key).strip()
        if not slug:
            continue
        digest = str(record.get("content_sha256") or "").strip()
        if digest:
            hashes[slug] = digest
        payload = record.get("payload")
        content = payload.get("content") if isinstance(payload, dict) else record.get("content")
        if isinstance(content, str):
            contents[slug] = content
    return hashes, contents

def _dirty_relpaths(repo: Path, paths: Iterable[Path]) -> list[str]:
    dirty = set(git.dirty_files(repo))
    result = []
    for path in paths:
        if not _inside(repo, path):
            continue
        rel = path.resolve().relative_to(repo.resolve()).as_posix()
        if rel in dirty:
            result.append(rel)
    return result


INSTRUCTION_PREFIXES = ("ins.", "rol.", "ctx.", "spc.")


def sync_instruction(repo: Path, *, slug: str, path: str, source_path: str,
                     remote_present: bool, local_dirty: bool) -> dict[str, Any]:
    if not slug.startswith(INSTRUCTION_PREFIXES):
        raise ObsError(f"expected an instruction slug prefix {INSTRUCTION_PREFIXES}, got: {slug or '<empty>'}")
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ObsError(f"{slug}: referenced instruction file does not exist: {source}")

    record, generated_hash = _render_body_record(
        repo, slug=slug, source=source, source_path=source_path or str(source)
    )
    if remote_present and not local_dirty:
        return {
            "slug": slug,
            "status": "current",
            "content_sha256": generated_hash,
            "uploaded": False,
            "committed": [],
        }

    result = run(
        [autoscribe_bin(), "upload", "instructions"],
        cwd=repo,
        input_text=json.dumps(_upload_envelope(record), ensure_ascii=False) + "\n",
    )
    return {
        "slug": slug,
        "status": "uploaded",
        "content_sha256": generated_hash,
        "uploaded": True,
        "committed": [],
        "commit": None,
        "pipeline_output": result.stdout.strip(),
    }


def sync_instructions(repo: Path, instruction_sets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reconcile referenced instruction files against authoritative remote hashes."""
    unique: dict[str, dict[str, Any]] = {}
    for item in instruction_sets:
        slug = str(item.get("slug") or "").strip()
        if not slug:
            raise ObsError("instruction component missing slug")
        raw_path = str(item.get("abspath") or item.get("path") or "").strip()
        if not raw_path:
            raise ObsError(f"{slug}: instruction component requires path")
        source = Path(raw_path).expanduser().resolve()
        if not source.is_file():
            raise ObsError(f"{slug}: referenced instruction file does not exist: {source}")
        if not _inside(repo, source):
            raise ObsError(f"{slug}: instruction file is outside the active vault: {source}")
        relpath = source.relative_to(repo.resolve()).as_posix()
        prior = unique.get(slug)
        if prior and prior["relpath"] != relpath:
            raise ObsError(f"instruction slug {slug} resolves to both {prior['relpath']} and {relpath}")
        unique[slug] = {**item, "source": source, "relpath": relpath}

    uploaded_hashes, uploaded_contents = _instruction_remote_state(pipeline_snapshot("control"))
    return [
        sync_instruction(
            repo,
            slug=slug,
            path=str(item["source"]),
            source_path=str(item.get("source_path") or item["relpath"]),
            remote_present=slug in uploaded_hashes or slug in uploaded_contents,
            local_dirty=item["relpath"] in set(git.dirty_files(repo)),
        )
        for slug, item in unique.items()
    ]


def upload_instruction(repo: Path, *, source_path: str, input_path: Path,
                       metadata_path: Path | None = None, force: bool = False,
                       commit: bool = True) -> dict[str, Any]:
    """Upload one instruction component; frontmatter is never included in content."""
    source = (repo / source_path).resolve()
    if not _inside(repo, source):
        raise ObsError(f"source path escapes vault: {source_path}")
    if not source.is_file():
        raise ObsError("source instruction file does not exist")
    document = parse_markdown(source.read_text(encoding="utf-8"))
    slug = str(document.frontmatter.get("slug") or "").strip()
    if not slug.startswith(INSTRUCTION_PREFIXES):
        raise ObsError(f"{source_path}: expected an instruction slug prefix {INSTRUCTION_PREFIXES}")
    record, digest = _render_body_record(repo, slug=slug, source=source, source_path=source_path)
    uploaded_hashes, uploaded_contents = _instruction_remote_state(pipeline_snapshot("control"))
    uploaded = uploaded_hashes.get(slug)
    if not force and (uploaded == digest or uploaded_contents.get(slug) == record["payload"]["content"]):
        return {"slug": slug, "status": "current", "content_sha256": digest}
    result = run(
        [autoscribe_bin(), "upload", "instructions"],
        cwd=repo,
        input_text=json.dumps(_upload_envelope(record), ensure_ascii=False) + "\n",
    )
    committed: list[str] = []
    commit_hash = None
    if commit:
        committed = _dirty_relpaths(repo, [source])
        if committed:
            stamp = datetime.now().astimezone().isoformat(timespec="seconds")
            commit_hash = git.commit_files(repo, committed, f"UPLOAD instruction: {slug} {stamp}")
    return {
        "slug": slug,
        "status": "uploaded",
        "content_sha256": digest,
        "committed": committed,
        "commit": commit_hash,
        "pipeline_output": result.stdout.strip(),
    }
