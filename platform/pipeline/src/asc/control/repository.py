"""Git-backed control catalog and plan store.

The authored Control repository remains ordinary source Git. Plans live in a
separate server-side Git repository and are written only through ``asc control``.
Redis is a materialized cache; enqueue may rebuild the records it needs from
these repositories at any time.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping

from asc.ingest.git_revision import ingest_path_from_revision


def control_repository() -> Path:
    return _repo_path("AUTOSCRIBE_CONTROL_REPO", "~/Work/Control")


def plan_repository() -> Path:
    return _repo_path(
        "AUTOSCRIBE_PLAN_REPO",
        "~/.local/share/autoscribe/control-plans.git",
        create_bare=True,
    )


def control_ref() -> str:
    return os.environ.get("AUTOSCRIBE_CONTROL_REF", "master").strip() or "master"


def plan_ref() -> str:
    return os.environ.get("AUTOSCRIBE_PLAN_REF", "master").strip() or "master"


def control_revision() -> str:
    return _revision(control_repository(), control_ref())


def plan_revision(*, required: bool = False) -> str | None:
    repo = plan_repository()
    result = _git_optional(repo, "rev-parse", "--verify", f"{plan_ref()}^{{commit}}")
    if result and result.strip():
        return result.strip()
    if required:
        raise RuntimeError(f"plan repository has no {plan_ref()} revision: {repo}")
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
    listing = _git(repo, "ls-tree", "-r", "--name-only", revision, "--", "instructions/")
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
    revision = plan_revision()
    if revision is None:
        return []
    repo = plan_repository()
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
        record.setdefault("source", "plan-git")
        record.setdefault("repo_commit", revision)
        records.append(record)
    selected = sorted(records, key=lambda item: _plan_identity(item))
    clean_scope = str(scope or "").strip()
    if not clean_scope:
        return selected
    return [record for record in selected if _plan_scope(record) == clean_scope]


def save_plan(record: Mapping[str, Any]) -> dict[str, str]:
    plan = _validated_plan_dict(record)
    identity = _plan_identity(plan)
    commit = _commit_plan(identity, plan, delete=False)
    return {"record_identity": identity, "commit": commit}


def delete_plan(identity: str) -> dict[str, str]:
    clean = _safe_identity(identity)
    commit = _commit_plan(clean, None, delete=True)
    return {"record_identity": clean, "commit": commit}


def materialize_plan(plan_slug: str) -> None:
    """Materialize the current Git plan and every instruction it references."""
    slug = _safe_identity(plan_slug)
    plan_repo = plan_repository()
    plan_commit = plan_revision(required=True)
    assert plan_commit is not None
    plan_path = f"plans/{slug}.json"
    plan = _json_at(plan_repo, plan_commit, plan_path)
    if _plan_identity(plan) != slug:
        raise RuntimeError(f"plan slug mismatch at {plan_path}: expected {slug}")

    instructions = _instruction_path_index()
    source_repo = control_repository()
    source_commit = control_revision()
    for instruction_slug in _instruction_slugs(plan):
        path = instructions.get(instruction_slug)
        if not path:
            raise KeyError(f"plan {slug} references unavailable instruction: {instruction_slug}")
        ingest_path_from_revision(
            source_repo,
            source_commit,
            path,
            repo_id=source_repo.name.removesuffix(".git"),
            repo_kind="control",
            trigger_ref=control_ref(),
        )

    # Re-ingesting the plan is content-addressed and refreshes its TTL while
    # ensuring Redis reflects the current plan Git revision.
    ingest_path_from_revision(
        plan_repo,
        plan_commit,
        plan_path,
        repo_id=plan_repo.name.removesuffix(".git"),
        repo_kind="control",
        trigger_ref=plan_ref(),
    )


def _instruction_path_index() -> dict[str, str]:
    return {record["slug"]: record["path"] for record in instruction_records()}


def _instruction_slugs(plan: Mapping[str, Any]) -> tuple[str, ...]:
    payload = plan.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("plan payload must be an object")
    steps = payload.get("steps")
    if not isinstance(steps, Mapping) or not steps:
        raise ValueError("plan requires steps")
    found: list[str] = []
    seen: set[str] = set()
    for step in steps.values():
        if not isinstance(step, Mapping):
            continue
        refs = step.get("instruction_slugs") or step.get("instructions") or {}
        if isinstance(refs, Mapping):
            values = refs.values()
        elif isinstance(refs, list):
            values = refs
        else:
            values = ()
        for value in values:
            entries = value if isinstance(value, list) else [value]
            for entry in entries:
                if isinstance(entry, str) and entry.strip() and entry.strip() not in seen:
                    clean = entry.strip()
                    seen.add(clean)
                    found.append(clean)
        legacy = step.get("instruction")
        if isinstance(legacy, str) and legacy.strip() and legacy.strip() not in seen:
            clean = legacy.strip()
            seen.add(clean)
            found.append(clean)
    return tuple(found)


def _validated_plan_dict(record: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(record)
    identity = _safe_identity(_plan_identity(value))
    payload = value.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError(f"{identity}: plan payload must be an object")
    steps = payload.get("steps")
    if not isinstance(steps, Mapping) or not steps:
        raise ValueError(f"{identity}: plan requires steps")
    value["record_identity"] = identity
    value.setdefault("record_type", "plan")
    if value.get("record_type") != "plan":
        raise ValueError(f"{identity}: record_type must be plan")
    return value


def _commit_plan(identity: str, record: Mapping[str, Any] | None, *, delete: bool) -> str:
    repo = plan_repository()
    branch = plan_ref()
    with tempfile.TemporaryDirectory(prefix="autoscribe-plan-") as temp:
        work = Path(temp) / "work"
        head = plan_revision()
        if head:
            _run(["git", "clone", "-q", "--branch", branch, str(repo), str(work)])
        else:
            work.mkdir()
            _run(["git", "-C", str(work), "init", "-q", f"--initial-branch={branch}"])
            _run(["git", "-C", str(work), "remote", "add", "origin", str(repo)])
        _run(["git", "-C", str(work), "config", "user.name", os.environ.get("AUTOSCRIBE_GIT_NAME", "AutoScribe Control")])
        _run(["git", "-C", str(work), "config", "user.email", os.environ.get("AUTOSCRIBE_GIT_EMAIL", "autoscribe@localhost")])
        relative = Path("plans") / f"{identity}.json"
        path = work / relative
        if delete:
            if not path.exists():
                raise KeyError(f"plan not found: {identity}")
            path.unlink()
            _run(["git", "-C", str(work), "add", "-A", "--", str(relative)])
            message = f"Delete plan {identity}"
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            _run(["git", "-C", str(work), "add", "--", str(relative)])
            message = f"Update plan {identity}"
        changed = _run_optional(["git", "-C", str(work), "diff", "--cached", "--quiet"])
        if changed.returncode == 0:
            return _git(work, "rev-parse", "HEAD").strip()
        _run(["git", "-C", str(work), "commit", "-q", "-m", message])
        _run(["git", "-C", str(work), "push", "-q", "origin", f"HEAD:{branch}"])
        return _git(work, "rev-parse", "HEAD").strip()


def _repo_path(env_name: str, default: str, *, create_bare: bool = False) -> Path:
    path = Path(os.environ.get(env_name, default)).expanduser().resolve()
    if path.exists():
        _git(path, "rev-parse", "--absolute-git-dir")
        return path
    if create_bare:
        path.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "init", "-q", "--bare", str(path)])
        return path
    raise FileNotFoundError(f"Git repository does not exist: {path} (set {env_name})")


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



def _plan_scope(record: Mapping[str, Any]) -> str:
    direct = record.get("scope")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    payload = record.get("payload")
    if isinstance(payload, Mapping):
        value = payload.get("scope")
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


def _git_optional(repo: Path, *args: str) -> str | None:
    result = _run_optional(["git", "-C", str(repo), *args])
    return result.stdout if result.returncode == 0 else None


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    result = _run_optional(args)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "command failed").strip())
    return result


def _run_optional(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)


__all__ = [
    "control_checkout", "control_ref", "control_repository", "control_revision", "delete_plan",
    "instruction_records", "materialize_plan", "plan_records", "plan_ref",
    "plan_repository", "plan_revision", "save_plan",
]
