from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from asc.models.control.plan import Plan
from asc.redis.key import RedisKey
from asc.state.slugmap import SlugMap


@dataclass(frozen=True, slots=True)
class LoadedPlan:
    """Resolved uploaded plan record with embedded step definitions."""

    slug: str
    plan_key: str
    plan: Plan

    @property
    def raw_key(self) -> str:
        return self.plan_key

    @property
    def step_count(self) -> int:
        return self.plan.total_steps


def load_plan(plan_slug: str) -> LoadedPlan:
    if not isinstance(plan_slug, str) or not plan_slug.strip():
        raise ValueError("plan must be a non-empty slug")

    clean_slug = plan_slug.strip()
    plan_key = resolve_plan_record_key(clean_slug)
    plan = Plan.load(plan_key)
    if not plan.steps:
        raise ValueError(f"plan has no embedded steps: {plan_key}")

    expected = list(range(1, plan.total_steps + 1))
    actual = list(plan.steps)
    if actual != expected:
        raise ValueError(
            f"plan step ordinals must be contiguous from 1: expected {expected}, got {actual}"
        )

    return LoadedPlan(slug=clean_slug, plan_key=plan_key, plan=plan)


def resolve_plan_record_key(plan_slug: str) -> str:
    resolved_key = SlugMap().get(plan_slug)
    if not resolved_key:
        raise KeyError(f"missing slugmap entry for plan: {plan_slug}")

    key = RedisKey(str(resolved_key))
    if key.kind != "plan":
        raise ValueError(f"record_plan resolved to non-plan key: {resolved_key}")
    if key.suffix in (None, "", "record"):
        return str(RedisKey(kind="plan", identity=key.identity, suffix="record"))
    raise ValueError(f"record_plan resolved to non-plan record key: {resolved_key}")


__all__ = ["LoadedPlan", "load_plan", "resolve_plan_record_key"]
