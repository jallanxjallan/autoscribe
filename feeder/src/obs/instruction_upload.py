from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import git
from .errors import ObsError
from .markdown import parse_markdown
from .pandoc import capture
from .process import run
from .executables import autoscribe_bin


def _metadata(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ObsError(f"metadata file must contain a mapping: {path}")
    return value


def upload_instruction(repo: Path, *, source_path: str, input_path: Path,
                       metadata_path: Path | None = None, force: bool = False,
                       commit: bool = True) -> dict[str, Any]:
    if not source_path:
        raise ObsError("instruction.upload requires source_path")
    source = (repo / source_path).resolve()
    if repo.resolve() not in source.parents:
        raise ObsError(f"source path escapes vault: {source_path}")
    if not source.is_file() or not input_path.is_file():
        raise ObsError("source instruction or resolved input file does not exist")
    document = parse_markdown(source.read_text(encoding="utf-8"))
    slug = str(document.frontmatter.get("slug") or "").strip()
    if not slug.startswith("ins."):
        raise ObsError(f"{source_path}: expected an ins.* slug")
    state = git.file_state(repo, source_path)
    if not force and state["repo_state"] == "clean":
        raise ObsError(f"{source_path}: instruction is clean; use force to re-upload")
    upload_commit = state.get("git_commit")
    if commit and state["repo_state"] != "clean":
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        upload_commit = git.commit_files(repo, [source_path], f"UPLOAD instruction: {slug} ({stamp})")
    metadata = _metadata(metadata_path)
    metadata.update({
        "slug": slug,
        "record_identity": slug,
        "record_type": "instruction",
        "source_path": source_path,
        "source_commit": upload_commit,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    })
    ndjson = capture(repo=repo, input_path=str(input_path), defaults=["upload_control"], metadata=metadata)
    result = run([autoscribe_bin(), "upload", "instructions"], cwd=repo, input_text=ndjson)
    response = result.stdout.strip()
    return {"slug": slug, "source_path": source_path, "input_path": str(input_path),
            "upload_commit": upload_commit, "pipeline_output": response}
