from dataclasses import dataclass

from asc.control.repository import read_plan
from asc.models.control.plan import Plan


@dataclass(frozen=True, slots=True)
class LoadedPlan:
    """Current immutable plan version read directly from Control Git."""

    slug: str
    revision: str
    path: str
    plan: Plan

    @property
    def raw_key(self) -> str:
        return self.source_ref

    @property
    def source_ref(self) -> str:
        return f"control-git@{self.revision}:{self.path}"

    @property
    def plan_key(self) -> str:
        """Compatibility field for reports; this is a Git ref, not a Redis key."""
        return self.source_ref

    @property
    def step_count(self) -> int:
        return self.plan.total_steps


def load_plan(plan_slug: str) -> LoadedPlan:
    if not isinstance(plan_slug, str) or not plan_slug.strip():
        raise ValueError("plan must be a non-empty slug")

    clean_slug = plan_slug.strip()
    source = read_plan(clean_slug)
    plan = source.plan
    if plan.slug != clean_slug:
        raise ValueError(
            f"plan slug mismatch: requested {clean_slug}, record contains {plan.slug}"
        )
    if not plan.steps:
        raise ValueError(f"plan has no embedded steps: {source.path}")

    expected = list(range(1, plan.total_steps + 1))
    actual = list(plan.steps)
    if actual != expected:
        raise ValueError(
            f"plan step ordinals must be contiguous from 1: expected {expected}, got {actual}"
        )

    return LoadedPlan(
        slug=clean_slug,
        revision=source.revision,
        path=source.path,
        plan=plan,
    )


def resolve_plan_record_key(plan_slug: str) -> str:
    """Compatibility alias returning the authoritative Git source reference."""
    return load_plan(plan_slug).plan_key


__all__ = ["LoadedPlan", "load_plan", "resolve_plan_record_key"]
