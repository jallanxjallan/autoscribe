from dataclasses import dataclass

from asc.models.control.plan import Plan
from asc.state.publications import resolve as resolve_publication


@dataclass(frozen=True, slots=True)
class LoadedPlan:
    """Resolved published plan record with embedded step definitions."""

    slug: str
    publication_ulid: str
    plan_key: str
    plan: Plan

    @property
    def raw_key(self) -> str:
        return self.plan_key

    @property
    def step_count(self) -> int:
        return self.plan.total_steps


def load_plan(plan_slug: str, *, publication_ulid: str | None = None) -> LoadedPlan:
    if not isinstance(plan_slug, str) or not plan_slug.strip():
        raise ValueError("plan must be a non-empty slug")

    clean_slug = plan_slug.strip()
    resolved_ulid, plan_key = resolve_publication(
        kind="plan", slug=clean_slug, publication_ulid=publication_ulid
    )
    plan = Plan.load(plan_key)
    if not plan.steps:
        raise ValueError(f"plan has no embedded steps: {plan_key}")

    expected = list(range(1, plan.total_steps + 1))
    actual = list(plan.steps)
    if actual != expected:
        raise ValueError(
            f"plan step ordinals must be contiguous from 1: expected {expected}, got {actual}"
        )

    return LoadedPlan(
        slug=clean_slug,
        publication_ulid=resolved_ulid,
        plan_key=plan_key,
        plan=plan,
    )


def resolve_plan_record_key(plan_slug: str, *, publication_ulid: str | None = None) -> str:
    return load_plan(plan_slug, publication_ulid=publication_ulid).plan_key


__all__ = ["LoadedPlan", "load_plan", "resolve_plan_record_key"]
