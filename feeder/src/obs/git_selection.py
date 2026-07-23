from __future__ import annotations

from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

from . import git
from .errors import ObsError
from .vault import Vault, VaultRecord

_CONFLICT_CODES = {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}


def _text(value: object) -> str:
    return str(value or "").strip()


def _relative_path(repo: Path, raw: object) -> str:
    value = _text(raw).replace("\\", "/")
    if not value:
        return ""

    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        try:
            return candidate.resolve(strict=False).relative_to(repo.resolve()).as_posix()
        except ValueError:
            raise ObsError(f"path is outside repository: {value}")

    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts:
        raise ObsError(f"path is outside repository: {value}")
    normalized = pure.as_posix().lstrip("./")
    if not normalized or normalized == ".":
        raise ObsError(f"invalid repository path: {value}")
    return normalized


def _known_paths(repo: Path, records: list[VaultRecord], statuses: list[dict[str, str]]) -> set[str]:
    paths = {record.path for record in records}
    paths.update(record["path"] for record in statuses if record.get("path"))
    for record in statuses:
        old = record.get("renamed_from")
        if old:
            paths.add(old)
    return paths


def _title_index(records: list[VaultRecord]) -> dict[str, list[VaultRecord]]:
    index: dict[str, list[VaultRecord]] = defaultdict(list)
    for record in records:
        candidates = {Path(record.path).stem}
        frontmatter_title = _text(record.frontmatter.get("title"))
        if frontmatter_title:
            candidates.add(frontmatter_title)
        for title in candidates:
            index[title.casefold()].append(record)
    return index


def _status_for(path: str, statuses: list[dict[str, str]]) -> dict[str, str] | None:
    for record in statuses:
        if record.get("path") == path:
            return record
        if record.get("renamed_from") == path:
            return record
    return None


def _repo_state(path: str, status: dict[str, str] | None, prior_commit: str) -> tuple[str, str]:
    if status is None:
        return ("clean" if prior_commit else "untracked", "")

    code = status.get("status", "")
    if code in _CONFLICT_CODES or "U" in code:
        return "conflicted", code
    if code == "??":
        return "untracked", code
    if "R" in code:
        return "renamed", code
    if "D" in code:
        return "deleted", code
    if "A" in code:
        return "added", code
    if "M" in code or "T" in code:
        return "modified", code
    return "dirty", code


def _latest_commit(repo: Path, path: str) -> dict[str, object] | None:
    return git.last_commit_record(repo, path)


def _resolve_one(
    repo: Path,
    raw: dict[str, Any],
    *,
    records: list[VaultRecord],
    slug_map: dict[str, VaultRecord],
    titles: dict[str, list[VaultRecord]],
    known_paths: set[str],
    statuses: list[dict[str, str]],
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "index": int(raw.get("index") or 0),
        "source_row": int(raw.get("source_row") or 0),
        "title": _text(raw.get("title")),
        "path": _text(raw.get("path")),
        "slug": _text(raw.get("slug")),
        "repo_state": "unknown",
        "git_status": "",
        "latest_commit": None,
        "committable": False,
        "error": "",
    }

    candidates: dict[str, str] = {}
    try:
        if item["path"]:
            path = _relative_path(repo, item["path"])
            if path not in known_paths and not (repo / path).is_file():
                raise ObsError(f"filepath does not resolve: {item['path']}")
            candidates["filepath"] = path

        if item["slug"]:
            record = slug_map.get(item["slug"])
            if record is None:
                raise ObsError(f"slug does not resolve: {item['slug']}")
            candidates["slug"] = record.path

        if item["title"]:
            matches = titles.get(item["title"].casefold(), [])
            unique = sorted({record.path for record in matches})
            if len(unique) > 1:
                raise ObsError(f"title is ambiguous: {item['title']}")
            if len(unique) == 1:
                candidates["title"] = unique[0]
            elif not candidates:
                raise ObsError(f"title does not resolve: {item['title']}")

        if not candidates:
            raise ObsError("row contains no resolvable filepath, slug, or title")

        resolved = set(candidates.values())
        if len(resolved) != 1:
            detail = ", ".join(f"{kind}={path}" for kind, path in candidates.items())
            raise ObsError(f"selection hints resolve to different files: {detail}")

        path = next(iter(resolved))
        record = next((entry for entry in records if entry.path == path), None)
        prior = git.last_commit(repo, path)
        status = _status_for(path, statuses)
        state, code = _repo_state(path, status, prior)

        item["path"] = path
        item["title"] = Path(path).stem
        if record is not None:
            item["slug"] = record.slug
            item["title"] = _text(record.frontmatter.get("title")) or Path(path).stem
        item["repo_state"] = state
        item["git_status"] = code
        item["latest_commit"] = _latest_commit(repo, path)

        if state == "clean":
            item["error"] = "file has no uncommitted changes"
        elif state == "conflicted":
            item["error"] = "file has unresolved merge conflicts"
        elif state == "unknown":
            item["error"] = "file state could not be determined"
        else:
            item["committable"] = True
    except (ObsError, OSError, ValueError) as exc:
        item["error"] = str(exc)

    return item


def resolve_selection(repo: Path, items: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(items, list):
        raise ObsError("git.resolve_selection requires items list")
    if not items:
        raise ObsError("git.resolve_selection requires at least one item")
    if not all(isinstance(item, dict) for item in items):
        raise ObsError("git.resolve_selection items must be objects")

    vault = Vault(repo)
    scan = vault.scan()
    records = scan.records
    statuses = git.status_records(repo)
    slug_map = {record.slug: record for record in records}
    titles = _title_index(records)
    known = _known_paths(repo, records, statuses)

    resolved = [
        _resolve_one(
            repo,
            item,
            records=records,
            slug_map=slug_map,
            titles=titles,
            known_paths=known,
            statuses=statuses,
        )
        for item in items
    ]

    by_path: dict[str, list[int]] = defaultdict(list)
    for position, item in enumerate(resolved):
        if item.get("path") and not item.get("error"):
            by_path[str(item["path"])].append(position)
    for path, positions in by_path.items():
        if len(positions) > 1:
            for position in positions:
                resolved[position]["committable"] = False
                resolved[position]["error"] = f"file appears more than once in selection: {path}"

    committable = sum(1 for item in resolved if item.get("committable"))
    return {
        "items": resolved,
        "summary": {
            "count": len(resolved),
            "committable": committable,
            "blocked": len(resolved) - committable,
            "scan_errors": [error.as_dict() for error in scan.errors],
        },
    }


def commit_selection(repo: Path, items: list[dict[str, Any]], message: str) -> dict[str, Any]:
    subject = _text(message)
    if not subject:
        raise ObsError("git.commit_selection requires message")

    resolved = resolve_selection(repo, items)
    blocked = [item for item in resolved["items"] if not item.get("committable")]
    if blocked:
        details = "; ".join(
            f"row {item.get('source_row') or item.get('index')}: {item.get('error') or 'not committable'}"
            for item in blocked
        )
        raise ObsError(f"commit selection is blocked: {details}")

    paths = [str(item["path"]) for item in resolved["items"]]
    commit_hash = git.commit_files(repo, paths, subject)
    return {
        "commit": {"hash": commit_hash, "subject": subject},
        "count": len(paths),
        "files": paths,
    }
