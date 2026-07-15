from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

from . import git
from .errors import ObsError
from .markdown import parse_markdown
from .process import run


def _asc_bin() -> str:
    return os.environ.get("AUTOSCRIBE_BIN") or os.environ.get("ASC_BIN") or "asc"


def pipeline_snapshot(kind: str) -> dict[str, Any]:
    commands = {
        "registry": ["registry", "snapshot"],
        "control": ["control", "snapshot"],
    }
    if kind not in commands:
        raise ObsError(f"unsupported pipeline snapshot: {kind}")
    result = run([_asc_bin(), *commands[kind]], cwd=Path.cwd())
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise ObsError(f"asc {kind} snapshot did not return an object")
    return value


def _roots(active: Path, roots: Iterable[str] | None, library_vault: str | None) -> list[Path]:
    values = [active]
    if roots:
        values.extend(Path(value).expanduser().resolve() for value in roots)
    if library_vault:
        values.append(Path(library_vault).expanduser().resolve())
    seen: set[Path] = set()
    result = []
    for value in values:
        value = value.resolve()
        if value in seen or not value.is_dir():
            continue
        seen.add(value)
        result.append(value)
    return result


def _local_instruction(active: Path, root: Path, path: Path) -> dict[str, Any] | None:
    document = parse_markdown(path.read_text(encoding="utf-8"))
    slug = str(document.frontmatter.get("slug") or "").strip()
    if not slug.startswith("ins."):
        return None
    rel = path.relative_to(root).as_posix()
    state = git.file_state(root, rel) if (root / ".git").exists() else {"repo_state": "untracked-repository"}
    return {
        "slug": slug,
        "kind": "instruction",
        "label": str(document.frontmatter.get("title") or document.frontmatter.get("label") or path.stem),
        "source": "active" if root == active else ("library" if root.name == "Library" else root.name),
        "root": str(root),
        "path": rel,
        "abspath": str(path),
        **state,
    }


def instruction_catalog(active: Path, *, roots: Iterable[str] | None = None,
                        library_vault: str | None = None, include_pipeline: bool = True) -> list[dict[str, Any]]:
    active = active.resolve()
    merged: dict[str, dict[str, Any]] = {}
    for root in _roots(active, roots, library_vault):
        for path in sorted(root.rglob("*.md")):
            rel = path.relative_to(root)
            if any(part in {".git", ".obsidian", "_control"} for part in rel.parts):
                continue
            record = _local_instruction(active, root, path)
            if not record:
                continue
            prior = merged.get(record["slug"])
            if prior is None or (prior.get("source") != "active" and record["source"] == "active"):
                merged[record["slug"]] = record
    if include_pipeline:
        snapshot = pipeline_snapshot("control")
        registries = snapshot.get("registries") if isinstance(snapshot, dict) else {}
        candidates = []
        if isinstance(registries, dict):
            for name in ("instructions", "controls"):
                values = registries.get(name)
                if isinstance(values, dict):
                    candidates.extend(values.values())
                elif isinstance(values, list):
                    candidates.extend(values)
        for raw in candidates:
            if not isinstance(raw, dict):
                continue
            slug = str(raw.get("slug") or raw.get("record_identity") or "").strip()
            if not slug.startswith("ins."):
                continue
            pipeline = {**raw, "slug": slug, "kind": "instruction", "pipeline": True, "source": "pipeline"}
            if slug in merged:
                merged[slug] = {**pipeline, **merged[slug], "pipeline": True, "pipeline_record": raw}
            else:
                merged[slug] = pipeline
    return sorted(merged.values(), key=lambda item: (str(item.get("source")), str(item.get("label") or item["slug"])))
