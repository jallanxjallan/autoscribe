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


def _canonical_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _render_record(repo: Path, *, slug: str, paths: list[Path], source_path: str) -> tuple[dict[str, Any], str]:
    metadata = {
        "slug": slug,
        "record_identity": slug,
        "record_type": "instruction",
        "source_path": source_path,
        "source_paths": [str(path) for path in paths],
    }
    ndjson = capture(
        repo=repo,
        input_paths=[str(path) for path in paths],
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


def sync_instruction(repo: Path, *, slug: str, paths: list[str], source_path: str,
                     uploaded_hashes: dict[str, str]) -> dict[str, Any]:
    if not slug.startswith("ins."):
        raise ObsError(f"expected an ins.* slug, got: {slug or '<empty>'}")
    if len(paths) != 3:
        raise ObsError(f"{slug}: expected ordered role, context, specific paths")

    resolved = [Path(value).expanduser().resolve() for value in paths]
    for path in resolved:
        if not path.is_file():
            raise ObsError(f"{slug}: referenced instruction file does not exist: {path}")

    specific = resolved[-1]
    document = parse_markdown(specific.read_text(encoding="utf-8"))
    actual_slug = str(document.frontmatter.get("slug") or "").strip()
    if actual_slug != slug:
        raise ObsError(f"{specific}: expected slug {slug}, found {actual_slug or '<empty>'}")

    record, generated_hash = _render_record(
        repo, slug=slug, paths=resolved, source_path=source_path
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

    with tempfile.TemporaryDirectory(prefix="obs-instruction-") as temp_dir:
        output_path = Path(temp_dir) / "instruction.ndjson"
        output_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
        result = run(
            ["/usr/bin/zsh", "-lc", f"cat {output_path.as_posix()!r} | {autoscribe_bin()!r} upload instructions"],
            cwd=repo,
        )

    dirty = _dirty_relpaths(repo, resolved)
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
    hashes = _instruction_hashes(pipeline_snapshot("control"))
    results = []
    for item in instruction_sets:
        paths = item.get("paths")
        if not isinstance(paths, list):
            raise ObsError("instruction set requires paths list")
        results.append(sync_instruction(
            repo,
            slug=str(item.get("slug") or "").strip(),
            paths=[str(value) for value in paths],
            source_path=str(item.get("source_path") or "").strip(),
            uploaded_hashes=hashes,
        ))
    return results


def upload_instruction(repo: Path, *, source_path: str, input_path: Path,
                       metadata_path: Path | None = None, force: bool = False,
                       commit: bool = True) -> dict[str, Any]:
    """Compatibility entry point for the older preassembled-file command."""
    source = (repo / source_path).resolve()
    if not _inside(repo, source):
        raise ObsError(f"source path escapes vault: {source_path}")
    if not source.is_file() or not input_path.is_file():
        raise ObsError("source instruction or resolved input file does not exist")
    document = parse_markdown(source.read_text(encoding="utf-8"))
    slug = str(document.frontmatter.get("slug") or "").strip()
    if not slug.startswith("ins."):
        raise ObsError(f"{source_path}: expected an ins.* slug")

    metadata: dict[str, Any] = {}
    if metadata_path is not None:
        import yaml
        raw = yaml.safe_load(metadata_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ObsError(f"metadata file must contain a mapping: {metadata_path}")
        metadata.update(raw)
    metadata.update({
        "slug": slug,
        "record_identity": slug,
        "record_type": "instruction",
        "source_path": source_path,
    })
    ndjson = capture(
        repo=repo, input_path=str(input_path), defaults=["upload_control"], metadata=metadata
    )
    lines = [line for line in ndjson.splitlines() if line.strip()]
    if len(lines) != 1:
        raise ObsError(f"{slug}: Pandoc produced {len(lines)} records; expected exactly one")
    record = json.loads(lines[0])
    digest = _canonical_hash(record)
    record["content_sha256"] = digest
    uploaded = _instruction_hashes(pipeline_snapshot("control")).get(slug)
    if not force and uploaded == digest:
        return {"slug": slug, "status": "current", "content_sha256": digest}
    result = run(
        [autoscribe_bin(), "upload", "instructions"],
        cwd=repo,
        input_text=json.dumps(record, ensure_ascii=False) + "\n",
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
