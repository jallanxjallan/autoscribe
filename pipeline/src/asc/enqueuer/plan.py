from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any

from asc.redis.key import RedisKey
from asc.redis.primitives.keys import exists
from asc.state.slugmap import SlugMap


@dataclass(frozen=True, slots=True)
class LoadedPlan:
    """Resolved uploaded-plan namespace plus materialized step keys."""

    slug: str
    plan_key: str
    step_keys: tuple[str, ...]

    @property
    def raw_key(self) -> str:
        return self.plan_key

    @property
    def step_count(self) -> int:
        return len(self.step_keys)


def load_plan_from_manifest_record(record: Mapping[str, Any]) -> LoadedPlan:
    """Resolve the top-level record_plan field emitted by dispatch-run.

    Plan upload no longer stores a Plan model. The slugmap value is a namespace
    pointer such as ``plan:<identity>``. That pointer is allowed to be a logical
    namespace only; the executable process is the materialized step set
    ``step:<identity>:<n>``.
    """

    try:
        plan_slug = record["record_plan"]
    except KeyError as exc:
        raise ValueError("enqueue record missing required field: record_plan") from exc

    if not isinstance(plan_slug, str) or not plan_slug.strip():
        raise ValueError("record_plan must be a non-empty string")

    clean_slug = plan_slug.strip()
    resolved_key = resolve_plan_namespace(clean_slug)
    step_keys = materialized_step_keys(resolved_key)

    return LoadedPlan(
        slug=clean_slug,
        plan_key=resolved_key,
        step_keys=step_keys,
    )


def resolve_plan_namespace(plan_slug: str) -> str:
    """Resolve a plan slug without requiring ``plan:<identity>`` to exist.

    ``SlugKeyResolver`` is intentionally not used here because it validates that
    the resolved key exists. Uploaded plans now publish a namespace pointer and
    executable step records, but no stored Plan hash.
    """

    resolved_key = SlugMap().get(plan_slug)
    if not resolved_key:
        raise KeyError(f"missing slugmap entry for plan: {plan_slug}")

    key = RedisKey(str(resolved_key))
    if key.kind != "plan":
        raise ValueError(f"record_plan resolved to non-plan key: {resolved_key}")

    return str(key)


def materialized_step_keys(plan_key: str) -> tuple[str, ...]:
    """Return sequential step keys for a previously uploaded plan namespace."""

    key = RedisKey(plan_key)
    if key.kind != "plan":
        raise ValueError(f"resolved plan key must have kind 'plan': {plan_key}")

    keys: list[str] = []
    number = 1
    while True:
        step_key = RedisKey(kind="step", identity=key.identity, suffix=number)
        if not exists(step_key):
            break
        keys.append(str(step_key))
        number += 1

    if not keys:
        raise ValueError(f"no materialized steps for plan: {plan_key}")

    return tuple(keys)


__all__ = [
    "LoadedPlan",
    "load_plan_from_manifest_record",
    "materialized_step_keys",
    "resolve_plan_namespace",
]
