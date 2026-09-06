"""Read trusted canonical Control directly from immutable Git objects."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from asc.config.repos import CONTROL
from asc.models.control.plan import Plan, SCOPES

GIT = Path(__file__).with_name("git.py").resolve()


@dataclass(frozen=True, slots=True)
class GitInstruction:
    identity: str
    title: str
    content: str
    path: str
    revision: str
    fingerprint: str
    extra: dict[str, Any]


@dataclass(frozen=True, slots=True)
class GitPlan:
    slug: str
    path: str
    revision: str
    plan: Plan


@dataclass(frozen=True, slots=True)
class ControlSnapshot:
    revision: str
    instructions: dict[str, GitInstruction]
    plans: dict[str, GitPlan]
    capabilities: dict[str, dict[str, dict[str, Any]]]


def _git(repo: Path, *args: str, missing_ok: bool = False) -> str:
    result = subprocess.run(
        [sys.executable, str(GIT), "-C", str(repo), *args],
        capture_output=True,
        check=False,
    )
    if missing_ok and result.returncode == 1:
        return ""
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).decode("utf-8").strip())
    return result.stdout.decode("utf-8")


def control_repository() -> Path:
    repo = CONTROL.path.expanduser().resolve()
    if not repo.exists():
        raise FileNotFoundError(f"Git repository does not exist: {repo}")
    return repo


def control_ref() -> str:
    return CONTROL.config_branch


def control_revision() -> str:
    return _git(
        control_repository(), "rev-parse", "--verify", f"{control_ref()}^{{commit}}"
    ).strip()


def _immutable_revision(revision: str) -> str:
    if not isinstance(revision, str) or not re.fullmatch(
        r"[0-9a-f]{40}|[0-9a-f]{64}", revision
    ):
        raise ValueError("Control revision must be a complete immutable commit ID")
    actual = _git(
        control_repository(), "rev-parse", "--verify", f"{revision}^{{commit}}"
    ).strip()
    if actual != revision:
        raise ValueError("Control revision must identify a commit")
    return revision


def _split_frontmatter(text: str, path: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise ValueError(f"{path}: instruction requires YAML frontmatter")
    end = next(
        (i for i in range(1, len(lines)) if lines[i].rstrip("\r\n") == "---"), None
    )
    if end is None:
        raise ValueError(f"{path}: unterminated YAML frontmatter")
    try:
        fields = yaml.safe_load("".join(lines[1:end]))
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: cannot parse canonical YAML") from exc
    return fields, "".join(lines[end + 1 :])


def _objects(repo: Path, revision: str, *paths: str):
    listing = _git(repo, "ls-tree", "-rz", revision, "--", *paths)
    for entry in listing.split("\x00"):
        if not entry:
            continue
        metadata, path = entry.split("\t", 1)
        mode, kind, oid = metadata.split()
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ValueError(f"{path}: Control requires ordinary files")
        yield path, oid


class ControlRepository:
    """A small read-through view of one commit; no authoring validation.

    Filenames are nonsemantic in Control. Git searches locate declarations;
    only requested records are parsed, and each blob is read once per view.
    """

    def __init__(self, revision: str | None = None):
        self.revision = (
            control_revision() if revision is None else _immutable_revision(revision)
        )
        self.repo = control_repository()
        self._plans: dict[str, GitPlan] = {}
        self._instructions: dict[str, GitInstruction] = {}

    @classmethod
    def at_revision(cls, revision: str) -> ControlRepository:
        return cls(revision)

    def _find(self, pattern: str, *paths: str):
        output = _git(
            self.repo,
            "grep",
            "-l",
            "-z",
            "-E",
            "-e",
            pattern,
            self.revision,
            "--",
            *paths,
            missing_ok=True,
        )
        for match in output.split("\0"):
            if match:
                yield match.removeprefix(self.revision + ":")

    def _blob(self, path: str) -> tuple[str, str]:
        entries = dict(_objects(self.repo, self.revision, path))
        oid = entries[path]
        return oid, _git(self.repo, "show", oid)

    def _plan(self, path: str) -> GitPlan:
        if path not in self._plans:
            _, text = self._blob(path)
            try:
                record = json.loads(text, parse_constant=_invalid_constant)
            except ValueError as exc:
                raise ValueError(
                    f"{path} at {self.revision}: cannot parse canonical JSON"
                ) from exc
            plan = Plan(**record)
            self._plans[path] = GitPlan(plan.slug, path, self.revision, plan)
        return self._plans[path]

    def _instruction(self, path: str) -> GitInstruction:
        if path not in self._instructions:
            oid, text = self._blob(path)
            fields, body = _split_frontmatter(text, path)
            identity = fields["identity"]
            self._instructions[path] = GitInstruction(
                identity,
                fields["title"],
                body,
                path,
                self.revision,
                oid,
                {
                    "description": fields["description"],
                    "scope": SCOPES[identity[:3]],
                    "repo_commit": self.revision,
                    "repo_path": path,
                },
            )
        return self._instructions[path]

    def read_plan(self, slug: str) -> GitPlan:
        pattern = r'"slug"[[:space:]]*:[[:space:]]*' + re.escape(json.dumps(slug))
        for path in self._find(pattern, "plans/*.json"):
            source = self._plan(path)
            if source.slug == slug:
                return source
        raise KeyError(f"missing plan: {slug} at Control revision {self.revision}")

    def read_instruction(self, identity: str) -> GitInstruction:
        pattern = (
            r"^identity:[[:space:]]*['\"]?"
            + re.escape(identity)
            + r"['\"]?[[:space:]]*$"
        )
        for path in self._find(pattern, "instructions/*.md", "context/*.md"):
            source = self._instruction(path)
            if source.identity == identity:
                return source
        raise KeyError(
            f"missing instruction: {identity} at Control revision {self.revision}"
        )


def _invalid_constant(value: str):
    raise ValueError(f"non-JSON numeric constant: {value}")


def read_plan(plan_slug: str, revision: str | None = None) -> GitPlan:
    return ControlRepository(revision).read_plan(plan_slug)


def read_instruction(instruction_identity: str, revision: str) -> GitInstruction:
    return ControlRepository.at_revision(revision).read_instruction(
        instruction_identity
    )


def list_revision(revision: str | None = None) -> ControlSnapshot:
    """Enumerate Control for administrative displays, separately from enqueue."""
    control = ControlRepository(revision)
    instructions = {}
    plans = {}
    capabilities = {
        name: {} for name in ("engines", "models", "local_scripts", "rag_profiles")
    }
    for path, _ in _objects(
        control.repo, control.revision, "instructions/", "context/", "plans/"
    ):
        if path.endswith(".md"):
            source = control._instruction(path)
            instructions[source.identity] = source
        elif path.endswith(".json"):
            source = control._plan(path)
            plans[source.slug] = source
            for name, records in source.plan.capabilities.items():
                capabilities[name].update(records)
    return ControlSnapshot(control.revision, instructions, plans, capabilities)


def instruction_records(
    snapshot: ControlSnapshot | None = None,
) -> list[dict[str, Any]]:
    snapshot = snapshot if snapshot is not None else list_revision()
    return [
        {
            "identity": item.identity,
            "title": item.title,
            "path": item.path,
            "source_fingerprint": item.fingerprint,
            **item.extra,
        }
        for _, item in sorted(snapshot.instructions.items())
    ]


def plan_records(
    scope: str | None = None, *, snapshot: ControlSnapshot | None = None
) -> list[dict[str, Any]]:
    snapshot = snapshot if snapshot is not None else list_revision()
    return [
        item.plan.plan_dict() | {"repo_commit": snapshot.revision, "path": item.path}
        for _, item in sorted(snapshot.plans.items())
        if scope is None or item.plan.scope == scope
    ]
