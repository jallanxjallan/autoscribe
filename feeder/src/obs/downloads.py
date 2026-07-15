from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import git
from .errors import ObsError
from .manifests import now_iso, write_json
from .markdown import parse_markdown, render_markdown, strip_frontmatter
from .process import run
from .executables import autoscribe_bin
from .state import VaultState
from .vault import Vault


def _ndjson(text: str) -> list[dict[str, Any]]:
    values = []
    for line in text.splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ObsError("expected NDJSON objects")
            values.append(value)
    return values


def _first_string(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def pending_exports(repo: Path) -> list[dict[str, Any]]:
    output = run([autoscribe_bin(), "export", "list-pending-exports"], cwd=repo).stdout
    records = []
    for raw in _ndjson(output):
        records.append({
            "prompt_slug": _first_string(raw, "record_identity", "prompt_slug"),
            "call_identity": _first_string(raw, "call_identity"),
            "result_identity": _first_string(raw, "result_identity"),
            "raw": raw,
        })
    for index, record in enumerate(records, 1):
        if not all(record[key] for key in ("prompt_slug", "call_identity", "result_identity")):
            raise ObsError(f"pending export {index}: missing slug, call identity, or result identity")
    unique = {record["result_identity"]: record for record in records}
    return list(unique.values())


def _extract_content(value: Any, seen: set[str] | None = None) -> str:
    seen = seen or set()
    if isinstance(value, dict):
        for key in ("record_content", "result_content", "content", "body", "text"):
            if key in value:
                return _extract_content(value[key], seen)
        return ""
    if not isinstance(value, str) or not value.strip():
        return ""
    text = value.strip()
    if text in seen:
        return text
    seen.add(text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text
    nested = _extract_content(parsed, seen)
    return nested or text


def extract_result(repo: Path, item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    output = run([autoscribe_bin(), "export", "extract-result", item["call_identity"]], cwd=repo).stdout
    records = _ndjson(output)
    if len(records) != 1:
        raise ObsError(f"expected exactly one extracted result record, got {len(records)}")
    content = _extract_content(records[0])
    if not content.strip():
        raise ObsError(f"{item['prompt_slug']}: extracted result is empty")
    return content, records[0]


def mark_exported(repo: Path, result_identity: str) -> None:
    run([autoscribe_bin(), "export", "update-exports", result_identity], cwd=repo)


def writeback(repo: Path, *, dry_run: bool = False, limit: int | None = None) -> list[dict[str, Any]]:
    vault = Vault(repo)
    slug_map = vault.slug_map(public_only=True)
    dirty = git.dirty_tracked_files(repo)
    selected = [item for item in pending_exports(repo) if item["prompt_slug"] in slug_map]
    if limit is not None:
        selected = selected[:limit]
    prepared = []
    for item in selected:
        target = slug_map[item["prompt_slug"]]
        if not git.last_commit(repo, target.path):
            raise ObsError(f"{target.path}: target file has never been committed")
        if target.path in dirty:
            raise ObsError(f"{target.path}: target file is already dirty")
        content, raw = extract_result(repo, item)
        document = parse_markdown((repo / target.path).read_text(encoding="utf-8"))
        if not document.has_frontmatter:
            raise ObsError(f"{target.path}: target file has no frontmatter to preserve")
        body = strip_frontmatter(_extract_content(content)).lstrip("\n")
        if not body.strip():
            raise ObsError(f"{target.path}: result body is empty")
        frontmatter = dict(document.frontmatter)
        frontmatter["status"] = "ai-generated"
        prepared.append({**item, "path": target.path, "content": render_markdown(frontmatter, body), "raw_result": raw})
    if dry_run:
        return prepared
    for item in prepared:
        path = repo / item["path"]
        old = path.read_text(encoding="utf-8")
        if old != item["content"]:
            path.write_text(item["content"], encoding="utf-8")
        mark_exported(repo, item["result_identity"])
    _write_manifest(repo, "writeback", prepared)
    return prepared


def writenew(repo: Path, *, target_dir: str = "new", dry_run: bool = False,
             limit: int | None = None) -> list[dict[str, Any]]:
    vault = Vault(repo)
    known = vault.slug_map(public_only=True)
    selected = [item for item in pending_exports(repo)
                if item["prompt_slug"].startswith("prv.") and item["prompt_slug"] not in known]
    if limit is not None:
        selected = selected[:limit]
    target_root = (repo / target_dir).resolve()
    if repo.resolve() not in (target_root, *target_root.parents):
        raise ObsError(f"target dir escapes vault root: {target_dir}")
    prepared = []
    reserved: set[Path] = set()
    for item in selected:
        content, raw = extract_result(repo, item)
        body = strip_frontmatter(_extract_content(content)).lstrip("\n")
        if not body.strip():
            raise ObsError(f"{item['prompt_slug']}: result body is empty")
        stem = _filename_stem(item["raw"], raw)
        target = _allocate(target_root, stem, reserved)
        prepared.append({**item, "path": target.relative_to(repo).as_posix(), "content": body, "raw_result": raw})
    if dry_run:
        return prepared
    for item in prepared:
        path = repo / item["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise ObsError(f"{item['path']}: target appeared before writenew")
        path.write_text(item["content"].rstrip() + "\n", encoding="utf-8")
        mark_exported(repo, item["result_identity"])
    _write_manifest(repo, "writenew", prepared, target_dir)
    return prepared


def _filename_stem(*sources: Any) -> str:
    keys = ("filename_hint", "filename", "file_name", "source_path", "path", "title", "name", "label")
    def walk(value: Any) -> str:
        if isinstance(value, dict):
            for key in keys:
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate
            for child in value.values():
                result = walk(child)
                if result:
                    return result
        elif isinstance(value, list):
            for child in value:
                result = walk(child)
                if result:
                    return result
        return ""
    raw = next((walk(source) for source in sources if walk(source)), "")
    raw = raw.split("?")[0].split("#")[0].replace("\\", "/").rsplit("/", 1)[-1]
    raw = re.sub(r"\.[A-Za-z0-9]{1,12}$", "", raw)
    clean = re.sub(r"[<>:\"/\\|?*\x00-\x1f]+", " ", raw).strip(" .")
    return clean[:120] or "Untitled"


def _allocate(directory: Path, stem: str, reserved: set[Path]) -> Path:
    for number in range(1, 10000):
        suffix = "" if number == 1 else f" {number:03d}"
        path = directory / f"{stem}{suffix}.md"
        if path not in reserved and not path.exists():
            reserved.add(path)
            return path
    raise ObsError("could not allocate a new Markdown filename")


def _write_manifest(repo: Path, mode: str, items: list[dict[str, Any]], target_dir: str | None = None) -> None:
    path = VaultState.for_vault(repo).writing(mode)
    value = {"type": "writing_manifest", "mode": mode, "created": now_iso(),
             "vault_root": str(repo), "storage": "local-share", "target_dir": target_dir,
             "items": [{key: item[key] for key in ("prompt_slug", "call_identity", "result_identity", "path")}
                       for item in items]}
    write_json(path, value)
