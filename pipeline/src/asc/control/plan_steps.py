from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from asc.models.control.plan import PlanRecord
from asc.models.control.plan_step import PlanStepRecord
from asc.models.runtime.step import RuntimeStepDefinition
from asc.redis.key import RedisKey

try:  # Current name after the prompt/control slugmap merge.
    from asc.state.slugmap import SLUGMAP_TTL_SECONDS, SlugMap
except ModuleNotFoundError:  # Compatibility with the pre-merge state package.
    from asc.state.control_slugmap import (  # type: ignore[no-redef]
        CONTROL_SLUGMAP_TTL_SECONDS as SLUGMAP_TTL_SECONDS,
        ControlSlugMap as SlugMap,
    )


Resolver = Callable[[str, str], str]


@dataclass(frozen=True, slots=True)
class UploadedPlan:
    plan: PlanRecord
    plan_key: str
    step_keys: tuple[str, ...]

    @property
    def step_count(self) -> int:
        return len(self.step_keys)


class PlanStepIndex:
    """Ordered index of compiled control step hashes for one uploaded plan."""

    def __init__(self, plan_identity: str) -> None:
        self.plan_identity = plan_identity
        self.key = RedisKey.from_parts("control", plan_identity, "plan-step-index")

    def clear(self) -> None:
        for step_key in self.keys():
            RedisKey(step_key).delete()
        self.key.delete()

    def bind_key(self, step_number: int, step_key: str) -> None:
        self.key.hset(field=str(step_number), value=step_key)

    def keys(self) -> list[str]:
        mapping = self.key.hgetall()
        return [
            mapping[str(step_number)]
            for step_number in sorted(int(position) for position in mapping)
        ]


def upload_plan_record(record: Mapping[str, Any], *, slugmap: object | None = None) -> UploadedPlan:
    """Validate, save, and compile one public plan upload record.

    The public plan manifest may be UI-rich: engine/script/RAG/instruction
    references can be full registry/control objects. This upload boundary is
    the one place where controlled normalization is allowed. The compiled plan
    steps saved below are worker-ready scalar step definitions.
    """

    plan = PlanRecord.model_validate(dict(record))
    if not plan.steps:
        raise ValueError("plan must include at least one executable step")

    resolver = SlugKeyResolver(slugmap)
    plan_key = plan.save()
    index = PlanStepIndex(plan.identity)
    index.clear()

    step_keys: list[str] = []
    for step_number, raw_step in enumerate(plan.steps, start=1):
        compiled = compile_plan_step(raw_step, resolve_control_key=resolver.resolve)
        step_record = PlanStepRecord.from_definition(
            plan_identity=plan.identity,
            plan_slug=plan.record_identity,
            step_number=step_number,
            definition=compiled,
        )
        step_key = step_record.save()
        index.bind_key(step_number, step_key)
        step_keys.append(step_key)

    resolver.bind(plan.record_identity, plan_key)
    return UploadedPlan(plan=plan, plan_key=plan_key, step_keys=tuple(step_keys))


def compile_plan_step(step: Mapping[str, Any], *, resolve_control_key: Resolver) -> dict[str, Any]:
    """Compile one UI-rich public plan step into a worker-ready definition."""

    normalized = normalize_plan_step(step)
    return (
        RuntimeStepDefinition.model_validate(normalized)
        .resolved(resolve_control_key=resolve_control_key)
        .to_runtime_dict()
    )


def normalize_plan_step(step: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a saved plan-manifest step into scalar runtime input.

    Saved plan manifests are allowed to retain rich UI metadata such as:

        engine: {key: "engines.scripts", ...}
        script: {key: "scripts.insert_header", ...}
        instructions: [{slug: "ins.foo"}, ...]

    RuntimeStepDefinition is intentionally stricter. It wants scalar engine
    strings, instruction slugs, and executable arguments. This function performs
    that low-frequency upload-boundary conversion once, during control upload.
    """

    raw = dict(step)
    args = _object_dict(raw.get("args"), field="args")

    engine = _ref_text(raw.get("engine"), field="engine", required=False)
    if not engine:
        engine = _ref_text(args.get("engine"), field="args.engine", required=True)

    kind = _optional_text(raw.get("kind") or raw.get("step_kind") or raw.get("type"))
    label = _optional_text(raw.get("label"))
    model = _optional_text(raw.get("model"))
    script = _ref_text(raw.get("script"), field="script", required=False)
    rag_profile = _ref_text(raw.get("rag_profile"), field="rag_profile", required=False)

    # Lift executable refs from rich top-level UI records into args as strings.
    args["engine"] = engine
    if model and not args.get("model"):
        args["model"] = model
    if script:
        args["script"] = script
    elif args.get("script") is not None:
        args["script"] = _ref_text(args.get("script"), field="args.script", required=True)
    if rag_profile:
        args["rag_profile"] = rag_profile
    elif args.get("rag_profile") is not None:
        args["rag_profile"] = _ref_text(args.get("rag_profile"), field="args.rag_profile", required=True)

    instructions = _instruction_slugs(raw)

    compiled: dict[str, Any] = {
        "engine": engine,
        "instructions": instructions,
        "args": args,
    }
    if kind:
        compiled["kind"] = kind
    if label:
        compiled["label"] = label
    if model:
        compiled["model"] = model

    return compiled


def _instruction_slugs(step: Mapping[str, Any]) -> list[str]:
    values: list[str] = []

    raw_slugs = step.get("instruction_slugs")
    if raw_slugs is not None:
        if not isinstance(raw_slugs, list):
            raise ValueError("instruction_slugs must be a list")
        values.extend(_ref_text(item, field="instruction_slugs[]", required=True) for item in raw_slugs)

    raw_instructions = step.get("instructions")
    if raw_instructions is not None:
        if not isinstance(raw_instructions, list):
            raise ValueError("instructions must be a list")
        values.extend(_ref_text(item, field="instructions[]", required=True) for item in raw_instructions)

    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def _ref_text(value: object, *, field: str, required: bool) -> str:
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return ""

    if isinstance(value, str):
        text = value.strip()
        if text:
            return text
        if required:
            raise ValueError(f"{field} must be a non-empty string")
        return ""

    if isinstance(value, Mapping):
        for key in ("key", "slug", "record_identity", "identity", "module"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()

    raise ValueError(f"{field} must be a string or object with key/slug/record_identity")


def _optional_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _object_dict(value: object, *, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return dict(value)


def load_plan_step_definitions(plan_identity: str) -> list[dict[str, Any]]:
    """Load compiled executable step definitions for enqueue/runtime use."""

    definitions: list[dict[str, Any]] = []
    for step_key in PlanStepIndex(plan_identity).keys():
        step = PlanStepRecord.load_from_key(step_key)
        definitions.append(step.definition)
    return definitions


class SlugKeyResolver:
    """Resolve source slugs into full Redis keys during control upload."""

    def __init__(self, slugmap: object | None = None) -> None:
        self._slugmap = slugmap or SlugMap()

    def bind(self, slug: str, key: str) -> None:
        for method_name in ("bind", "set_key", "store", "record"):
            method = getattr(self._slugmap, method_name, None)
            if callable(method):
                try:
                    method(slug, key, ttl=SLUGMAP_TTL_SECONDS)
                except TypeError:
                    method(slug, key)
                return
        raise TypeError("SlugMap must provide bind(), set_key(), store(), or record()")

    def resolve(self, value: str, expected_kind: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("slug/key reference must be a non-empty string")

        reference = value.strip()
        if ":" in reference:
            return self._validate_full_key(reference, expected_kind=expected_kind)
        return self._resolve_slug(reference, expected_kind=expected_kind)

    def _resolve_slug(self, slug: str, *, expected_kind: str) -> str:
        for method_name in ("resolve_key", "get_key", "lookup_key"):
            method = getattr(self._slugmap, method_name, None)
            if callable(method):
                try:
                    return str(method(slug, require=True, expected_kind=expected_kind))
                except TypeError:
                    return str(method(slug, expected_kind=expected_kind))
        raise TypeError("SlugMap must provide resolve_key(), get_key(), or lookup_key()")

    def _validate_full_key(self, key: str, *, expected_kind: str) -> str:
        redis_key = RedisKey(key)
        actual_kind = redis_key.segments[-1] if redis_key.segments else None
        if actual_kind != expected_kind:
            raise ValueError(
                f"key kind mismatch: expected {expected_kind}, got {actual_kind} ({key})"
            )
        if not redis_key.exists():
            raise KeyError(f"missing key: {key}")
        redis_key.expire(SLUGMAP_TTL_SECONDS)
        return str(redis_key)


__all__ = [
    "PlanStepIndex",
    "SlugKeyResolver",
    "UploadedPlan",
    "compile_plan_step",
    "load_plan_step_definitions",
    "normalize_plan_step",
    "upload_plan_record",
]
