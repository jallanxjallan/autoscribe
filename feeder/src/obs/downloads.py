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
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ObsError(f"invalid NDJSON on line {line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise ObsError(f"expected NDJSON object on line {line_number}")
        values.append(value)
    return values


def _first_string(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


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


def _normalise_pending_response(raw: dict[str, Any], index: int) -> dict[str, Any]:
    prompt_slug = _first_string(raw, "record_identity", "source_identity", "prompt_slug", "slug")
    call_identity = _first_string(raw, "call_identity", "call", "identity")
    result_identity = _first_string(raw, "result_identity", "response_identity", "identity", "call_identity")
    missing = [
        name
        for name, value in (
            ("prompt slug", prompt_slug),
            ("call identity", call_identity),
            ("result identity", result_identity),
        )
        if not value
    ]
    if missing:
        raise ObsError(f"pending response {index}: missing {', '.join(missing)}")
    return {
        "prompt_slug": prompt_slug,
        "call_identity": call_identity,
        "result_identity": result_identity,
    }


def _normalise_response(raw: dict[str, Any], index: int) -> dict[str, Any]:
    response = _normalise_pending_response(raw, index)
    content = _extract_content(raw)
    if not content:
        raise ObsError(f"extracted response {index}: missing response content")
    response["content"] = content
    response["raw"] = raw
    return response


def pending_responses(repo: Path) -> list[dict[str, Any]]:
    """Return lightweight unexported response metadata for panel matching."""
    output = run([autoscribe_bin(), "export", "list-pending", "--ndjson"], cwd=repo).stdout
    records = [_normalise_pending_response(raw, index) for index, raw in enumerate(_ndjson(output), 1)]
    unique: dict[str, dict[str, Any]] = {}
    for record in records:
        unique[record["result_identity"]] = record
    return list(unique.values())


def extract_results(repo: Path, slugs: list[str]) -> list[dict[str, Any]]:
    """Extract and receipt a selected slug batch in one asc invocation."""
    cleaned = [str(slug).strip() for slug in slugs]
    if not cleaned or any(not slug for slug in cleaned):
        raise ObsError("extract requires at least one non-empty slug")
    if len(cleaned) != len(set(cleaned)):
        raise ObsError("extract slug list contains duplicates")
    output = run([autoscribe_bin(), "export", "extract-selected", *cleaned], cwd=repo).stdout
    records = [_normalise_response(raw, index) for index, raw in enumerate(_ndjson(output), 1)]
    by_slug = {record["prompt_slug"]: record for record in records}
    if len(by_slug) != len(records):
        raise ObsError("asc export returned duplicate response slugs")
    missing = [slug for slug in cleaned if slug not in by_slug]
    unexpected = [slug for slug in by_slug if slug not in set(cleaned)]
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected: {', '.join(unexpected)}")
        raise ObsError("asc export batch did not match selection (" + "; ".join(details) + ")")
    return [by_slug[slug] for slug in cleaned]


def pending_exports(repo: Path) -> list[dict[str, Any]]:
    output = run([autoscribe_bin(), "export", "list-pending", "--ndjson"], cwd=repo).stdout
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


def _validated_write_target(repo: Path, raw: dict[str, Any], *, allow_dirty: bool) -> dict[str, Any]:
    prompt_slug = _first_string(raw, "prompt_slug", "record_identity", "slug")
    call_identity = _first_string(raw, "call_identity", "call")
    result_identity = _first_string(raw, "result_identity", "response_identity", "identity")
    relpath = _first_string(raw, "path")
    if not all((prompt_slug, call_identity, result_identity, relpath)):
        raise ObsError("write response item requires slug, call identity, result identity, and path")

    target = (repo / relpath).resolve()
    if repo.resolve() not in target.parents:
        raise ObsError(f"{relpath}: target escapes vault root")
    if not target.is_file():
        raise ObsError(f"{relpath}: target file does not exist")

    current_slug_map = Vault(repo).slug_map(public_only=True)
    current_target = current_slug_map.get(prompt_slug)
    if current_target is None or current_target.path != relpath:
        raise ObsError(f"{relpath}: slug no longer resolves to {prompt_slug}")
    if not git.last_commit(repo, relpath):
        raise ObsError(f"{relpath}: target file has never been committed")

    dirty = relpath in git.dirty_tracked_files(repo)
    if dirty and not allow_dirty:
        raise ObsError(f"{relpath}: target file is dirty")

    document = parse_markdown(target.read_text(encoding="utf-8"))
    if not document.has_frontmatter:
        raise ObsError(f"{relpath}: target file has no frontmatter to preserve")
    return {
        "prompt_slug": prompt_slug,
        "call_identity": call_identity,
        "result_identity": result_identity,
        "path": relpath,
        "frontmatter": dict(document.frontmatter),
        "was_dirty": dirty,
    }


def write_responses(repo: Path, items: list[dict[str, Any]], *, allow_dirty: bool = False,
                    dry_run: bool = False) -> list[dict[str, Any]]:
    if not isinstance(items, list) or not items:
        raise ObsError("responses.write requires a non-empty items list")
    prepared = [_validated_write_target(repo, item, allow_dirty=allow_dirty) for item in items]
    paths = [item["path"] for item in prepared]
    slugs = [item["prompt_slug"] for item in prepared]
    if len(paths) != len(set(paths)):
        raise ObsError("multiple selected responses target the same file")
    if len(slugs) != len(set(slugs)):
        raise ObsError("multiple selected files use the same slug")

    if dry_run:
        return prepared

    # This one call both extracts the selected responses and creates their export
    # receipts. The panel has already matched slugs and the feeder has rechecked
    # every target immediately above.
    extracted = extract_results(repo, slugs)
    by_slug = {item["prompt_slug"]: item for item in extracted}

    written: list[dict[str, Any]] = []
    for item in prepared:
        response = by_slug[item["prompt_slug"]]
        body = strip_frontmatter(response["content"]).lstrip("\n")
        if not body.strip():
            raise ObsError(f"{item['path']}: response body is empty")
        frontmatter = dict(item.pop("frontmatter"))
        frontmatter["status"] = "ai-generated"
        rendered = render_markdown(frontmatter, body)
        path = repo / item["path"]
        old = path.read_text(encoding="utf-8")
        changed = old != rendered
        if changed:
            path.write_text(rendered, encoding="utf-8")
        written.append({**item, **response, "content": rendered, "changed": changed})
    _write_manifest(repo, "writeback", written)
    return written


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


def _commit_member_targets(repo: Path, commit_hash: str) -> list[dict[str, Any]]:
    """Resolve the Markdown members of a dispatch commit to current files by slug."""
    commit = str(commit_hash or "").strip()
    if not commit:
        raise ObsError("commit hash is required")
    current = Vault(repo).slug_map(public_only=True)
    items: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    for source_path in git.files_in_commit(repo, commit):
        if Path(source_path).suffix.lower() != ".md":
            continue
        document = parse_markdown(git.show_file(repo, commit, source_path))
        slug = str(document.frontmatter.get("slug") or "").strip()
        if not slug:
            raise ObsError(f"{source_path}: missing slug in dispatch commit")
        if slug in seen_slugs:
            raise ObsError(f"dispatch commit contains duplicate slug: {slug}")
        seen_slugs.add(slug)
        target = current.get(slug)
        if target is None:
            items.append({
                "source_path": source_path, "slug": slug, "path": None,
                "state": "unresolved", "git_status": "", "dirty": False,
                "error": "slug does not resolve to a current file",
            })
            continue
        state = git.file_state(repo, target.path)
        dirty = bool(state["git_status"])
        items.append({
            "source_path": source_path, "slug": slug, "path": target.path,
            "state": state["repo_state"], "git_status": state["git_status"],
            "dirty": dirty, "error": None,
        })
    if not items:
        raise ObsError("selected dispatch commit contains no Markdown files")
    return items


def writeback_candidates(repo: Path, *, limit: int = 100) -> list[dict[str, Any]]:
    records = []
    for commit in git.inflight_commit_records(repo, limit=limit):
        members = _commit_member_targets(repo, str(commit["hash"]))
        records.append({**commit, "members": members,
                        "blocked": any(item["dirty"] or item["error"] for item in members)})
    return records


def writeback_commit_selection(repo: Path, *, commit_hash: str, dry_run: bool = False) -> dict[str, Any]:
    commit = str(commit_hash or "").strip()
    candidates = {str(item["hash"]): item for item in git.inflight_commit_records(repo, limit=500)}
    selected = candidates.get(commit)
    if selected is None:
        raise ObsError("selected commit is not an available inflight dispatch")

    members = _commit_member_targets(repo, commit)
    blocked = [item for item in members if item["dirty"] or item["error"]]
    if blocked:
        details = "; ".join(
            f"{item.get('path') or item['source_path']}: {item.get('error') or item['git_status'] or 'dirty'}"
            for item in blocked
        )
        raise ObsError(f"writeback aborted because selected files are not clean: {details}")

    items = []
    for member in members:
        path = str(member["path"])
        document = parse_markdown((repo / path).read_text(encoding="utf-8"))
        if not document.has_frontmatter:
            raise ObsError(f"{path}: target file has no frontmatter to preserve")
        items.append({"prompt_slug": member["slug"], "path": path,
                      "frontmatter": dict(document.frontmatter)})

    if dry_run:
        return {"commit": commit, "plan_slug": selected["plan_slug"],
                "inflight_tag": selected["inflight_tag"], "members": members,
                "written": [], "writeback_commit": None, "dry_run": True}

    extracted = extract_results(repo, [item["prompt_slug"] for item in items])
    by_slug = {item["prompt_slug"]: item for item in extracted}
    originals = {item["path"]: (repo / item["path"]).read_text(encoding="utf-8") for item in items}
    written: list[dict[str, Any]] = []
    try:
        for item in items:
            response = by_slug[item["prompt_slug"]]
            body = strip_frontmatter(response["content"]).lstrip("\n")
            if not body.strip():
                raise ObsError(f"{item['path']}: response body is empty")
            frontmatter = dict(item["frontmatter"])
            frontmatter["status"] = "ai-generated"
            rendered = render_markdown(frontmatter, body)
            path = repo / item["path"]
            changed = originals[item["path"]] != rendered
            if changed:
                path.write_text(rendered, encoding="utf-8")
            written.append({
                "path": item["path"], "prompt_slug": item["prompt_slug"],
                "changed": changed, "result_identity": response["result_identity"],
                "call_identity": response["call_identity"],
            })
        changed_paths = [item["path"] for item in written if item["changed"]]
        if not changed_paths:
            raise ObsError("writeback produced no file changes")
        wb_commit = git.writeback_commit(
            repo, changed_paths, source_commit=commit,
            inflight_tag=str(selected["inflight_tag"]),
            plan_slug=str(selected["plan_slug"]),
        )
    except Exception:
        for path, content in originals.items():
            (repo / path).write_text(content, encoding="utf-8")
        raise

    _write_manifest(repo, "writeback", written)
    return {
        "commit": commit, "plan_slug": selected["plan_slug"],
        "inflight_tag": selected["inflight_tag"], "members": members,
        "written": written, "writeback_commit": wb_commit, "dry_run": False,
    }
