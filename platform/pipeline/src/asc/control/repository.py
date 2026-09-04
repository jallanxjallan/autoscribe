"""Git-backed published Control catalog.

One published Control bare repository and branch are authoritative for both
``instructions/`` and ``plans/``. Plans are authored in Control alongside
instructions; ``asc`` reads but does not author or mutate published Control.
Plans are always read from Git. Redis may cache instructions only as needed by
enqueue; it is never a durable Control store.
"""

from __future__ import annotations

import io
import json
import subprocess
import tarfile
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from asc.config.repos import CONTROL
from asc.models.control.plan import Plan


@dataclass(frozen=True, slots=True)
class GitInstruction:
    slug: str
    title: str
    content: str
    path: str
    revision: str
    commit_timestamp: int
    extra: dict[str, Any]


@dataclass(frozen=True, slots=True)
class GitPlan:
    slug: str
    path: str
    revision: str
    plan: Plan


def control_repository() -> Path:
    """Published Control Git repository containing authored configuration."""
    return _require_repo(CONTROL.path)


def plan_repository() -> Path:
    """Plans live in the same published Control repository as instructions."""
    return control_repository()


def control_ref() -> str:
    return CONTROL.config_branch


def plan_ref() -> str:
    """Compatibility alias: plans use the published Control ref."""
    return control_ref()


def control_revision() -> str:
    return _revision(control_repository(), control_ref())


def plan_revision(*, required: bool = False) -> str | None:
    """Compatibility alias: plans use the published Control revision."""
    try:
        return control_revision()
    except Exception:
        if required:
            raise
        return None



@contextmanager
def control_checkout():
    """Materialize the published Control Git tree into a temporary directory."""
    repo = control_repository()
    revision = control_revision()
    result = subprocess.run(
        ["git", "-C", str(repo), "archive", "--format=tar", revision],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", "replace").strip() or "git archive failed")
    with tempfile.TemporaryDirectory(prefix="autoscribe-control-") as temp:
        root = Path(temp)
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
            archive.extractall(root, filter="data")
        yield root

def instruction_records() -> list[dict[str, Any]]:
    repo = control_repository()
    revision = control_revision()
    listing = _git(
        repo,
        "ls-tree",
        "-r",
        "--name-only",
        revision,
        "--",
        "instructions/",
        "context/",
    )
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_path in listing.splitlines():
        path = raw_path.strip()
        if not path.endswith(".md"):
            continue
        text = _git(repo, "show", f"{revision}:{path}")
        frontmatter, _body = _split_frontmatter(text, path)
        kind = str(frontmatter.get("record") or frontmatter.get("type") or frontmatter.get("kind") or "").strip().lower()
        if kind and kind != "instruction":
            continue
        slug = str(frontmatter.get("slug") or "").strip()
        if not slug:
            continue
        if slug in seen:
            raise RuntimeError(f"duplicate committed instruction slug: {slug}")
        seen.add(slug)
        component = str(frontmatter.get("component") or frontmatter.get("class") or _component_from_slug(slug)).strip()
        title = str(frontmatter.get("title") or frontmatter.get("label") or Path(path).stem).strip()
        description = str(frontmatter.get("description") or frontmatter.get("summary") or "").strip()
        records.append({
            "type": "instruction",
            "slug": slug,
            "record_identity": slug,
            "title": title or slug,
            "label": title or slug,
            "description": description,
            "scope": component,
            "component": component,
            "path": path,
            "source": "control-git",
            "repo_commit": revision,
        })
    return sorted(records, key=lambda item: item["slug"])


def plan_records(scope: str | None = None) -> list[dict[str, Any]]:
    revision = control_revision()
    repo = control_repository()
    listing = _git(repo, "ls-tree", "-r", "--name-only", revision, "--", "plans/")
    records: list[dict[str, Any]] = []
    for raw_path in listing.splitlines():
        path = raw_path.strip()
        if not path.endswith(".json"):
            continue
        record = _json_at(repo, revision, path)
        identity = _plan_identity(record)
        if not identity:
            raise RuntimeError(f"{path}: plan requires record_identity")
        record = dict(record)
        record.setdefault("record_identity", identity)
        record.setdefault("slug", identity)
        record.setdefault("source", "control-git")
        record.setdefault("repo_commit", revision)
        records.append(record)
    selected = sorted(records, key=lambda item: _plan_identity(item))
    clean_scope = str(scope or "").strip()
    if not clean_scope:
        return selected
    return [record for record in selected if _plan_scope(record) == clean_scope]


def save_plan(record: Mapping[str, Any]) -> dict[str, str]:
    raise RuntimeError(
        "plans are authored in the Control repository; commit and push plans/*.json through the Control authoring workflow"
    )


def delete_plan(identity: str) -> dict[str, str]:
    raise RuntimeError(
        "plans are authored in the Control repository; delete and publish plans/*.json through the Control authoring workflow"
    )


def read_plan(plan_slug: str) -> GitPlan:
    """Read and validate the current plan directly from published Control Git."""
    slug = _safe_identity(plan_slug)
    repo = control_repository()
    revision = control_revision()
    listing = _git(repo, "ls-tree", "-r", "--name-only", revision, "--", "plans/")
    matches = [
        (path, record)
        for path in (raw.strip() for raw in listing.splitlines())
        if path.endswith(".json")
        for record in (_json_at(repo, revision, path),)
        if _plan_identity(record) == slug
    ]
    if not matches:
        raise KeyError(f"plan not found in Control Git: {slug}")
    if len(matches) != 1:
        raise RuntimeError(f"duplicate committed plan slug: {slug}")
    path, record = matches[0]
    content = _plan_content(record)
    try:
        plan = Plan.from_content(
            content,
            slug=slug,
            extra={"repo_commit": revision, "repo_path": path},
        )
        plan.identity = slug
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path}: invalid plan: {exc}") from exc
    if not plan.steps:
        raise ValueError(f"plan has no embedded steps: {path}")
    return GitPlan(slug=slug, path=path, revision=revision, plan=plan)


def read_instruction(instruction_slug: str) -> GitInstruction:
    """Read one current instruction and its last Git change timestamp."""
    slug = _safe_identity(instruction_slug)
    repo = control_repository()
    revision = control_revision()
    listing = _git(
        repo,
        "ls-tree",
        "-r",
        "--name-only",
        revision,
        "--",
        "instructions/",
        "context/",
    )
    matches: list[tuple[str, dict[str, str], str]] = []
    for path in (raw.strip() for raw in listing.splitlines()):
        if not path.endswith(".md"):
            continue
        frontmatter, body = _split_frontmatter(
            _git(repo, "show", f"{revision}:{path}"), path
        )
        if str(frontmatter.get("slug") or "").strip() == slug:
            matches.append((path, frontmatter, body))
    if not matches:
        raise KeyError(f"instruction not found in Control Git: {slug}")
    if len(matches) != 1:
        raise RuntimeError(f"duplicate committed instruction slug: {slug}")
    path, frontmatter, body = matches[0]
    actual_slug = str(frontmatter.get("slug") or "").strip()
    if actual_slug != slug:
        raise RuntimeError(
            f"instruction slug mismatch at {path}: expected {slug}, "
            f"got {actual_slug or '(blank)'}"
        )
    changed_at = _git(
        repo, "log", "-1", "--format=%ct", revision, "--", path
    ).strip()
    if not changed_at:
        raise RuntimeError(f"instruction has no Git commit timestamp: {path}")
    component = str(
        frontmatter.get("component")
        or frontmatter.get("class")
        or _component_from_slug(slug)
    ).strip()
    title = str(
        frontmatter.get("title") or frontmatter.get("label") or Path(path).stem
    ).strip()
    return GitInstruction(
        slug=slug,
        title=title or slug,
        content=body,
        path=path,
        revision=revision,
        commit_timestamp=int(changed_at),
        extra={
            "description": str(
                frontmatter.get("description") or frontmatter.get("summary") or ""
            ).strip(),
            "scope": component,
            "component": component,
            "repo_commit": revision,
            "repo_path": path,
            "repo_ref": control_ref(),
        },
    )


def _require_repo(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Git repository does not exist: {resolved}")
    _git(resolved, "rev-parse", "--absolute-git-dir")
    return resolved



def _revision(repo: Path, ref: str) -> str:
    return _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()


def _json_at(repo: Path, revision: str, path: str) -> Mapping[str, Any]:
    try:
        value = json.loads(_git(repo, "show", f"{revision}:{path}"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"{path}: expected JSON object")
    return value


def _split_frontmatter(text: str, path: str) -> tuple[dict[str, str], str]:
    lines = str(text).replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{path}: instruction Markdown requires YAML frontmatter")
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValueError(f"{path}: unterminated YAML frontmatter") from exc
    frontmatter: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        key = key.strip()
        value = raw.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            frontmatter[key] = value
    return frontmatter, "\n".join(lines[end + 1 :]).strip()



def _plan_content(record: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the compact plan content, accepting legacy ``payload`` records."""
    content = record.get("record_content")
    if not isinstance(content, Mapping):
        content = record.get("payload")
    if not isinstance(content, Mapping):
        identity = _plan_identity(record) or "(unknown plan)"
        raise ValueError(f"{identity}: plan record_content must be an object")
    return content


def _plan_scope(record: Mapping[str, Any]) -> str:
    direct = record.get("scope")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    content = record.get("record_content")
    if not isinstance(content, Mapping):
        content = record.get("payload")
    if isinstance(content, Mapping):
        value = content.get("scope")
        if isinstance(value, str):
            return value.strip()
    return ""

def _plan_identity(record: Mapping[str, Any]) -> str:
    return str(record.get("record_identity") or record.get("slug") or record.get("identity") or "").strip()


def _safe_identity(value: str) -> str:
    clean = str(value or "").strip()
    if not clean or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in clean):
        raise ValueError(f"invalid control identity: {clean or '(blank)'}")
    return clean


def _component_from_slug(slug: str) -> str:
    return {
        "std": "standing", "rul": "rule", "rol": "role", "ctx": "context",
        "tsk": "task", "ins": "task", "spc": "task",
    }.get(str(slug).split(".", 1)[0], "")


def _git(repo: Path, *args: str) -> str:
    result = _run_optional(["git", "-C", str(repo), *args])
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "Git command failed").strip())
    return result.stdout


def _run_optional(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)


__all__ = [
    "control_checkout", "control_ref", "control_repository", "control_revision", "delete_plan",
    "GitInstruction", "GitPlan", "instruction_records", "plan_records", "plan_ref",
    "plan_repository", "plan_revision", "read_instruction", "read_plan", "save_plan",
]
