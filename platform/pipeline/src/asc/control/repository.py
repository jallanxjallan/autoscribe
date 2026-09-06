"""Read and accept complete canonical Control snapshots directly from Git objects."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from asc.config.repos import CONTROL
from asc.models.control.plan import Plan, instruction_scope

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


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        [sys.executable, str(GIT), "-C", str(repo), *args],
        capture_output=True,
        check=False,
    )
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


class _UniqueLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader, node):
    pairs = loader.construct_pairs(node, deep=True)
    return _unique_object(pairs)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate field: {key}")
        result[key] = value
    return result


_UniqueLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping
)


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
        fields = yaml.load("".join(lines[1:end]), Loader=_UniqueLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: invalid YAML") from exc
    if not isinstance(fields, dict) or set(fields) != {
        "identity",
        "title",
        "description",
    }:
        raise ValueError(
            f"{path}: required instruction fields are identity, title, description"
        )
    instruction_scope(fields["identity"])
    for key in ("title", "description"):
        if not isinstance(fields[key], str) or "\x00" in fields[key]:
            raise ValueError(f"{path}: {key} must be text")
    body = "".join(lines[end + 1 :])
    if not fields["title"].strip() or not body.strip() or "\x00" in body:
        raise ValueError(f"{path}: title and body must be non-empty text")
    return fields, body


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


def accept_revision(revision: str | None = None) -> ControlSnapshot:
    """Reject the entire revision if any instruction, plan, or reference is invalid."""
    revision = (
        _immutable_revision(revision) if revision is not None else control_revision()
    )
    repo = control_repository()
    instructions = {}
    plans = {}
    capabilities = {
        name: {} for name in ("engines", "models", "local_scripts", "rag_profiles")
    }
    for path, oid in _objects(repo, revision, "instructions/", "context/"):
        if not path.endswith(".md"):
            continue
        fields, body = _split_frontmatter(_git(repo, "show", oid), path)
        identity = fields["identity"]
        if identity in instructions:
            raise ValueError(f"duplicate instruction identity: {identity}")
        instructions[identity] = GitInstruction(
            identity,
            fields["title"],
            body,
            path,
            revision,
            oid,
            {
                "description": fields["description"],
                "scope": instruction_scope(identity),
                "repo_commit": revision,
                "repo_path": path,
            },
        )
    for path, oid in _objects(repo, revision, "plans/"):
        if not path.endswith(".json"):
            continue
        try:
            record = json.loads(
                _git(repo, "show", oid),
                object_pairs_hook=_unique_object,
                parse_constant=_invalid_constant,
            )
            plan = Plan.model_validate(record)
            _validate_capabilities(plan)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{path}: invalid plan: {exc}") from exc
        if plan.slug in plans:
            raise ValueError(f"duplicate plan slug: {plan.slug}")
        for step in plan.steps.values():
            for identities in step["instructions"].values():
                for identity in identities:
                    if identity not in instructions:
                        raise ValueError(
                            f"{path}: missing instruction identity: {identity}"
                        )
        for registry, records in plan.capabilities.items():
            for key, metadata in records.items():
                previous = capabilities[registry].get(key)
                if previous is not None and previous != metadata:
                    raise ValueError(
                        f"conflicting capability metadata: {registry}.{key}"
                    )
                capabilities[registry][key] = metadata
        plans[plan.slug] = GitPlan(plan.slug, path, revision, plan)
    return ControlSnapshot(revision, instructions, plans, capabilities)


def _invalid_constant(value: str):
    raise ValueError(f"non-JSON numeric constant: {value}")


def _validate_args_schema(schema: Any) -> None:
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("capability requires an object args_schema")

    def check_refs(value):
        if isinstance(value, dict):
            for key in ("$ref", "$dynamicRef", "$recursiveRef", "$id"):
                if key in value and not str(value[key]).startswith("#"):
                    raise ValueError("capability schemas may only use local references")
            for item in value.values():
                check_refs(item)
        elif isinstance(value, list):
            for item in value:
                check_refs(item)

    check_refs(schema)
    Draft202012Validator.check_schema(schema)


def _validate_capabilities(plan: Plan) -> None:
    registries = plan.capabilities
    if set(registries) != {"engines", "models", "local_scripts", "rag_profiles"}:
        raise ValueError(
            "capabilities requires engines, models, local_scripts, rag_profiles registries"
        )
    for registry, records in registries.items():
        for key, metadata in records.items():
            if not key or key != key.strip():
                raise ValueError("capability keys must be non-empty canonical strings")
            _validate_args_schema(metadata.get("args_schema"))
            if registry == "engines":
                if metadata.get("kind") not in {"llm", "script", "rag"}:
                    raise ValueError(f"invalid engine kind: {key}")
                fields = metadata.get("step_fields")
                if not isinstance(fields, list) or any(
                    not isinstance(f, str) for f in fields
                ):
                    raise ValueError("engine requires step_fields array")
            if (
                registry == "models"
                and metadata.get("engine") not in registries["engines"]
            ):
                raise ValueError(f"model {key} references a missing engine")
    for step in plan.steps.values():
        engine = registries["engines"].get(step["engine"])
        if engine is None or engine.get("kind") != step["engine_kind"]:
            raise ValueError(f"missing or incompatible engine: {step['engine']}")
        fields = engine.get("step_fields")
        if not isinstance(fields, list) or any(not isinstance(f, str) for f in fields):
            raise ValueError("engine requires step_fields array")
        parameters = set(step) - {
            "engine",
            "engine_kind",
            "instructions",
            "args",
            "label",
        }
        if parameters - set(fields):
            raise ValueError(
                f"unsupported engine parameters: {parameters - set(fields)}"
            )
        field, registry = {
            "llm": ("model", "models"),
            "script": ("script", "local_scripts"),
            "rag": ("rag_profile", "rag_profiles"),
        }[step["engine_kind"]]
        if (set(step) & {"model", "script", "rag_profile"}) != {field}:
            raise ValueError("step must reference only its engine kind capability")
        reference = step.get(field)
        if not isinstance(reference, str) or reference not in registries[registry]:
            raise ValueError(f"missing {field} reference: {reference}")
        capability = registries[registry][reference]
        if field == "model" and capability.get("engine") != step["engine"]:
            raise ValueError("model belongs to a different engine")
        for metadata in (engine, capability):
            schema = metadata.get("args_schema")
            errors = list(Draft202012Validator(schema).iter_errors(step["args"]))
            if errors:
                raise ValueError(f"invalid capability args: {errors[0].message}")
        if "temperature" in step and (
            type(step["temperature"]) not in {int, float}
            or not 0 <= step["temperature"] <= 2
        ):
            raise ValueError("temperature must be numeric between 0 and 2")
        if "max_output_tokens" in step and (
            type(step["max_output_tokens"]) is not int or step["max_output_tokens"] < 1
        ):
            raise ValueError("max_output_tokens must be a positive integer")


def read_plan(plan_slug: str, revision: str | None = None) -> GitPlan:
    snapshot = accept_revision(revision)
    try:
        return snapshot.plans[plan_slug]
    except KeyError:
        raise KeyError(f"plan not found in Control Git: {plan_slug}") from None


def read_instruction(instruction_identity: str, revision: str) -> GitInstruction:
    instruction_scope(instruction_identity)
    snapshot = accept_revision(revision)
    try:
        return snapshot.instructions[instruction_identity]
    except KeyError:
        raise KeyError(
            f"instruction not found in Control Git: {instruction_identity}"
        ) from None


def instruction_records(
    snapshot: ControlSnapshot | None = None,
) -> list[dict[str, Any]]:
    snapshot = snapshot if snapshot is not None else accept_revision()
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
    snapshot = snapshot if snapshot is not None else accept_revision()
    return [
        item.plan.plan_dict() | {"repo_commit": snapshot.revision, "path": item.path}
        for _, item in sorted(snapshot.plans.items())
        if scope is None or item.plan.scope == scope
    ]
