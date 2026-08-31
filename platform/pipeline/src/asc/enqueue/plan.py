from dataclasses import dataclass

from asc.models.control.plan import Plan
from asc.redis.key import RedisKey
from asc.state.slugmap import SlugMap
from asc.control.repository import materialize_plan


@dataclass(frozen=True, slots=True)
class LoadedPlan:
    """Current immutable plan version resolved directly through the slug map."""

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
    # Git, not Redis, is authoritative for reusable controls. Refresh the
    # selected plan and any missing instruction dependencies at enqueue time.
    materialize_plan(clean_slug)
    resolved = SlugMap().get(clean_slug)
    if not resolved:
        raise KeyError(f"plan did not materialize into slugmap: {clean_slug}")
    key = RedisKey(str(resolved))
    if key.kind != "plan" or key.suffix not in (None, "", "record"):
        raise ValueError(f"plan resolved to non-plan record key: {resolved}")

    plan_key = str(RedisKey(kind="plan", identity=key.identity, suffix="record"))
    plan = Plan.load(plan_key)
    if plan.slug != clean_slug:
        raise ValueError(
            f"plan slug mismatch: requested {clean_slug}, record contains {plan.slug}"
        )
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
    return load_plan(plan_slug).plan_key


__all__ = ["LoadedPlan", "load_plan", "resolve_plan_record_key"]
