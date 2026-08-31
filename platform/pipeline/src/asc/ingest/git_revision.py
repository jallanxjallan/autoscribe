from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from asc.ingest.common import IngestInputError, IngestReport, IngestedItem
from asc.ingest.handlers.instructions import ingest_instruction
from asc.ingest.handlers.plan import ingest_plan
from asc.redis.key import RedisKey
from asc.state.slugmap import SlugMap

CONFIG_PREFIXES = ("instructions/", "plans/")


@dataclass(frozen=True, slots=True)
class ConfigChange:
    status: str
    path: str
    old_path: str | None = None


@dataclass(frozen=True, slots=True)
class RepositoryProvenance:
    repo_id: str
    repo_kind: str
    repo_uri: str
    trigger_ref: str | None = None


def ingest_git_revision(
    repository: str | Path,
    revision: str,
    *,
    base: str | None = None,
    full: bool = False,
    repo_id: str | None = None,
    repo_kind: str = "project",
    trigger_ref: str | None = None,
) -> IngestReport:
    repo = _repository(repository)
    commit = _revision(repo, revision)
    provenance = _provenance(
        repo,
        repo_id=repo_id,
        repo_kind=repo_kind,
        trigger_ref=trigger_ref,
    )

    if full:
        paths = _config_paths(repo, commit)
        items = tuple(_ingest_path(repo, commit, path, provenance) for path in paths)
        return _report(items)

    base_commit = _revision(repo, base) if base else _parent(repo, commit)
    if base_commit is None:
        changes = tuple(ConfigChange("A", path) for path in _config_paths(repo, commit))
    else:
        changes = _changes(repo, base_commit, commit)

    items: list[IngestedItem] = []
    for change in changes:
        if change.status == "D":
            _delete_path(repo, base_commit, change.path)
            continue
        if change.status == "R" and change.old_path:
            _delete_path(repo, base_commit, change.old_path)
        items.append(_ingest_path(repo, commit, change.path, provenance))
    return _report(tuple(items))



def ingest_path_from_revision(
    repository: str | Path,
    revision: str,
    path: str,
    *,
    repo_id: str | None = None,
    repo_kind: str = "control",
    trigger_ref: str | None = None,
) -> IngestedItem:
    """Materialize one known config path from one Git revision.

    This is the lazy-enqueue entry point. It deliberately shares the same
    normalization/provenance path as bulk ``asc ingest``.
    """
    repo = _repository(repository)
    commit = _revision(repo, revision)
    provenance = _provenance(
        repo, repo_id=repo_id, repo_kind=repo_kind, trigger_ref=trigger_ref
    )
    if not _is_config_path(path):
        raise IngestInputError(f"unsupported config path: {path}")
    return _ingest_path(repo, commit, path, provenance)

def _report(items: tuple[IngestedItem, ...]) -> IngestReport:
    by_type: dict[str, int] = {}
    for item in items:
        by_type[item.record_type] = by_type.get(item.record_type, 0) + 1
    return IngestReport(record_count=len(items), by_type=by_type, records=items)


def _repository(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.exists():
        raise IngestInputError(f"Git repository does not exist: {path}")

    # `git rev-parse --show-toplevel` deliberately fails in a bare repository.
    # Ingest is a server-side operation, so bare repositories are first-class.
    git_dir = _git(path, "rev-parse", "--absolute-git-dir").strip()
    if not git_dir:
        raise IngestInputError(f"not a Git repository: {path}")
    bare = _git(path, "rev-parse", "--is-bare-repository").strip().lower() == "true"
    if bare:
        return Path(git_dir).resolve()

    root = _git(path, "rev-parse", "--show-toplevel").strip()
    if not root:
        raise IngestInputError(f"not a Git worktree: {path}")
    return Path(root).resolve()


def _provenance(
    repo: Path,
    *,
    repo_id: str | None,
    repo_kind: str,
    trigger_ref: str | None,
) -> RepositoryProvenance:
    identity = (repo_id or repo.name.removesuffix(".git")).strip()
    if not identity:
        raise IngestInputError("repository identity must be non-empty")
    kind = str(repo_kind or "project").strip().lower()
    if kind not in {"project", "global", "control"}:
        raise IngestInputError(f"unsupported repository kind: {repo_kind!r}")
    ref = str(trigger_ref).strip() if trigger_ref is not None else None
    return RepositoryProvenance(
        repo_id=identity,
        repo_kind=kind,
        repo_uri=str(repo),
        trigger_ref=ref or None,
    )


def _revision(repo: Path, value: str | None) -> str:
    if not value or not str(value).strip():
        raise IngestInputError("revision must be a non-empty Git revision")
    return _git(repo, "rev-parse", "--verify", f"{str(value).strip()}^{{commit}}").strip()


def _parent(repo: Path, commit: str) -> str | None:
    output = _git_optional(repo, "rev-parse", "--verify", f"{commit}^1")
    return output.strip() if output is not None and output.strip() else None


def _config_paths(repo: Path, commit: str) -> tuple[str, ...]:
    output = _git(repo, "ls-tree", "-r", "--name-only", commit, "--", *CONFIG_PREFIXES)
    return tuple(
        path.strip()
        for path in output.splitlines()
        if _is_config_path(path.strip())
    )


def _changes(repo: Path, base: str, commit: str) -> tuple[ConfigChange, ...]:
    output = _git(
        repo,
        "diff",
        "--name-status",
        "--find-renames",
        base,
        commit,
        "--",
        *CONFIG_PREFIXES,
    )
    changes: list[ConfigChange] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        fields = line.split("\t")
        status = fields[0]
        code = status[0]
        if code == "R" and len(fields) >= 3:
            old_path, new_path = fields[1], fields[2]
            if _is_config_path(old_path) or _is_config_path(new_path):
                changes.append(ConfigChange("R", new_path, old_path))
        elif code in {"A", "M", "T"} and len(fields) >= 2 and _is_config_path(fields[1]):
            changes.append(ConfigChange("A" if code == "A" else "M", fields[1]))
        elif code == "D" and len(fields) >= 2 and _is_config_path(fields[1]):
            changes.append(ConfigChange("D", fields[1]))
    return tuple(changes)


def _is_config_path(path: str) -> bool:
    if path.startswith("plans/"):
        return path.endswith(".json")
    if path.startswith("instructions/"):
        return path.endswith(".json") or path.endswith(".md")
    return False


def _ingest_path(
    repo: Path,
    commit: str,
    path: str,
    provenance: RepositoryProvenance,
) -> IngestedItem:
    category = path.split("/", 1)[0]
    try:
        if category == "instructions":
            record = _instruction_source_at(repo, commit, path)
            normalized = _instruction_record(record, path)
            _attach_provenance(normalized, provenance, commit, path)
            return ingest_instruction(normalized)
        if category == "plans":
            record = _record_at(repo, commit, path)
            normalized = _plan_record(record, path)
            _attach_provenance(normalized, provenance, commit, path)
            return ingest_plan(normalized)
    except (TypeError, ValueError, KeyError) as exc:
        raise IngestInputError(f"{path}: {exc}") from exc
    raise IngestInputError(f"unsupported config path: {path}")


def _attach_provenance(
    record: dict[str, Any],
    provenance: RepositoryProvenance,
    commit: str,
    path: str,
) -> None:
    extra = dict(record.get("extra") or {})
    extra.update({
        "repo_id": provenance.repo_id,
        "repo_kind": provenance.repo_kind,
        "repo_uri": provenance.repo_uri,
        "repo_commit": commit,
        "repo_path": path,
    })
    if provenance.trigger_ref:
        extra["repo_ref"] = provenance.trigger_ref
    record["extra"] = extra


def _delete_path(repo: Path, commit: str | None, path: str) -> None:
    if not commit:
        return
    category = path.split("/", 1)[0]
    record = _instruction_source_at(repo, commit, path) if category == "instructions" else _record_at(repo, commit, path)
    normalized = _instruction_record(record, path) if category == "instructions" else _plan_record(record, path)
    slug = str(normalized["identity"]).strip()
    slugmap = SlugMap()
    old_key = slugmap.get(slug)
    slugmap.delete(slug)
    if old_key:
        RedisKey(old_key).delete()



def _instruction_source_at(repo: Path, commit: str, path: str) -> Mapping[str, Any]:
    if path.endswith(".json"):
        return _record_at(repo, commit, path)
    if path.endswith(".md"):
        return _instruction_markdown_at(repo, commit, path)
    raise IngestInputError(f"{path}: unsupported instruction source")


def _instruction_markdown_at(repo: Path, commit: str, path: str) -> Mapping[str, Any]:
    raw = _git(repo, "show", f"{commit}:{path}")
    frontmatter, body = _split_markdown_frontmatter(raw, path)
    slug = str(frontmatter.get("slug") or "").strip()
    if not slug:
        raise IngestInputError(f"{path}: missing instruction slug")
    kind = str(
        frontmatter.get("record")
        or frontmatter.get("type")
        or frontmatter.get("kind")
        or ""
    ).strip().lower()
    if kind and kind != "instruction":
        raise IngestInputError(f"{path}: expected instruction record; got {kind!r}")

    component = str(
        frontmatter.get("component")
        or frontmatter.get("class")
        or _infer_instruction_component(slug)
        or ""
    ).strip()
    title = str(
        frontmatter.get("title")
        or frontmatter.get("label")
        or Path(path).stem
    ).strip()
    description = str(
        frontmatter.get("description")
        or frontmatter.get("summary")
        or ""
    ).strip()

    return {
        "type": "instruction",
        "identity": slug,
        "content": body,
        "extra": {
            "title": title,
            "description": description,
            "scope": component,
            "component": component,
            "source_path": path,
        },
    }


def _split_markdown_frontmatter(raw: str, path: str) -> tuple[dict[str, str], str]:
    text = str(raw).replace("\\r\\n", "\\n")
    lines = text.split("\\n")
    if not lines or lines[0].strip() != "---":
        raise IngestInputError(f"{path}: instruction Markdown requires YAML frontmatter")
    try:
        end = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration as exc:
        raise IngestInputError(f"{path}: unterminated YAML frontmatter") from exc

    frontmatter: dict[str, str] = {}
    for line in lines[1:end]:
        match = re.match(r"^([A-Za-z0-9_-]+):\\s*(.*)$", line)
        if not match:
            continue
        value = match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        frontmatter[match.group(1)] = value

    body = "\\n".join(lines[end + 1:]).strip()
    if not body:
        raise IngestInputError(f"{path}: instruction content must not be empty")
    return frontmatter, body


def _infer_instruction_component(slug: str) -> str:
    prefix = str(slug).split(".", 1)[0]
    return {
        "std": "standing",
        "rul": "rule",
        "rol": "role",
        "ctx": "context",
        "tsk": "task",
        "ins": "task",
        "spc": "task",
    }.get(prefix, "")


def _record_at(repo: Path, commit: str, path: str) -> Mapping[str, Any]:
    raw = _git(repo, "show", f"{commit}:{path}")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IngestInputError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(value, Mapping):
        raise IngestInputError(f"{path}: config record must be a JSON object")
    return value


def _instruction_record(record: Mapping[str, Any], path: str) -> dict[str, Any]:
    if record.get("type") in {"instruction", "instructions"}:
        return {
            "type": "instruction",
            "identity": _required_text(record.get("identity"), path, "identity"),
            "content": record.get("content"),
            "extra": dict(record.get("extra") or {}),
        }
    slug = record.get("record_identity") or record.get("identity") or record.get("slug")
    payload = record.get("payload")
    if isinstance(payload, Mapping):
        content = payload.get("content") or payload.get("body")
        extra = {key: value for key, value in payload.items() if key not in {"content", "body"}}
    else:
        content = record.get("content")
        extra = dict(record.get("extra") or {})
    return {"type": "instruction", "identity": _required_text(slug, path, "instruction identity"), "content": content, "extra": extra}


def _plan_record(record: Mapping[str, Any], path: str) -> dict[str, Any]:
    if record.get("type") in {"plan", "plans"} and "content" in record:
        return {
            "type": "plan",
            "identity": _required_text(record.get("identity"), path, "identity"),
            "content": record.get("content"),
            "extra": dict(record.get("extra") or {}),
        }
    slug = record.get("record_identity") or record.get("identity") or record.get("slug")
    return {
        "type": "plan",
        "identity": _required_text(slug, path, "plan identity"),
        "content": record.get("payload"),
        "extra": {},
    }


def _required_text(value: object, path: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IngestInputError(f"{path}: missing {field}")
    return value.strip()


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "Git command failed"
        raise IngestInputError(message)
    return result.stdout


def _git_optional(repo: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


__all__ = ["ConfigChange", "RepositoryProvenance", "ingest_git_revision", "ingest_path_from_revision"]
