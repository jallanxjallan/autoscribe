from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from . import git
from .catalog import pipeline_snapshot
from .errors import ObsError
from .executables import autoscribe_bin
from .markdown import parse_markdown
from .pandoc import capture
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
    """Return the strict Instruction upload envelope.

    Pandoc may emit source metadata for feeder-side diagnostics, but the
    persisted Instruction model owns only its content. The ingest handler
    derives ``slug`` from ``record_identity``.
    """
    record_type = str(record.get("record_type") or "instruction").strip()
    record_identity = str(record.get("record_identity") or record.get("slug") or "").strip()
    if record_type != "instruction":
        raise ObsError(f"expected instruction record_type, got: {record_type or '<empty>'}")
    if not record_identity:
        raise ObsError("instruction record missing record_identity")

    raw_payload = record.get("payload")
    if not isinstance(raw_payload, dict):
        raise ObsError(f"{record_identity}: Pandoc instruction payload must be an object")

    content = raw_payload.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ObsError(f"{record_identity}: Pandoc instruction payload requires non-empty content")

    return {
        "record_type": "instruction",
        "record_identity": record_identity,
        "payload": {"content": content},
    }

def _canonical_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _render_body_record(repo: Path, *, slug: str, source: Path, source_path: str) -> tuple[dict[str, Any], str]:
    document = parse_markdown(source.read_text(encoding="utf-8"))
    actual_slug = str(document.frontmatter.get("slug") or "").strip()
    if actual_slug != slug:
        raise ObsError(f"{source}: expected slug {slug}, found {actual_slug or '<empty>'}")
    body = document.body
    if not body.strip():
        raise ObsError(f"{source}: instruction body is empty")

    metadata = {
        "slug": slug,
        "record_identity": slug,
        "record_type": "instruction",
        "source_path": source_path,
    }
    with tempfile.TemporaryDirectory(prefix="obs-instruction-body-") as temp_dir:
        body_path = Path(temp_dir) / source.name
        body_path.write_text(body, encoding="utf-8")
        ndjson = capture(
            repo=repo,
            input_path=str(body_path),
            defaults=["upload_control"],
            metadata=metadata,
        )
    lines = [line for line in ndjson.splitlines() if line.strip()]
    if len(lines) != 1:
        raise ObsError(f"{slug}: Pandoc produced {len(lines)} instruction records; expected exactly one")
    try:
        record = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise ObsError(f"{slug}: Pandoc produced invalid NDJSON: {exc}") from exc
    if not isinstance(record, dict):
        raise ObsError(f"{slug}: Pandoc instruction output is not an object")
    digest = _canonical_hash(record)
    record["content_sha256"] = digest
    return record, digest


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
                     uploaded_hashes: dict[str, str]) -> dict[str, Any]:
    if not slug.startswith(INSTRUCTION_PREFIXES):
        raise ObsError(f"expected an instruction slug prefix {INSTRUCTION_PREFIXES}, got: {slug or '<empty>'}")
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ObsError(f"{slug}: referenced instruction file does not exist: {source}")

    record, generated_hash = _render_body_record(
        repo, slug=slug, source=source, source_path=source_path or str(source)
    )
    uploaded_hash = uploaded_hashes.get(slug)
    if uploaded_hash == generated_hash:
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

    dirty = _dirty_relpaths(repo, [source])
    commit_hash = None
    if dirty:
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        commit_hash = git.commit_files(repo, dirty, f"UPLOAD instruction: {slug} {stamp}")

    return {
        "slug": slug,
        "status": "uploaded",
        "content_sha256": generated_hash,
        "previous_sha256": uploaded_hash,
        "uploaded": True,
        "committed": dirty,
        "commit": commit_hash,
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

    uploaded_hashes = _instruction_hashes(pipeline_snapshot("control"))
    return [
        sync_instruction(
            repo,
            slug=slug,
            path=str(item["source"]),
            source_path=str(item.get("source_path") or item["relpath"]),
            uploaded_hashes=uploaded_hashes,
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
    uploaded = _instruction_hashes(pipeline_snapshot("control")).get(slug)
    if not force and uploaded == digest:
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
