from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from asc.models.control.plan import Plan
from asc.state.slugmap import SlugKeyResolver


# Future modification note:
# This module currently resolves manifest rows that reference persistent plans
# already uploaded and stored separately. It will later also handle ephemeral
# plans: plan content uploaded inline with the calls, containing instruction and
# script references that are valid only for that run and should not be stored as
# permanent reusable Plan records.
#
# When that work is done, keep this module as the enqueue-time plan-normalizing
# boundary. It should return the plan key or plan object needed by Call creation,
# but it should not create runtime cursors, call indexes, step indexes, worker
# tasks, or orchestrator state. Those are orchestrator/handler responsibilities.


@dataclass(frozen=True, slots=True)
class LoadedPlan:
    """A manifest-resolved Plan plus enqueue-time validation metadata.

    Future cleanup note:
    step_count is now report/validation metadata only. The orchestrator call
    handler reloads the plan and creates the runtime indexes. If reports no
    longer need step_count, this can be slimmed down to a resolved plan slug/key
    wrapper.
    """

    slug: str
    plan: Plan
    step_count: int

    @property
    def raw_key(self) -> str:
        return str(self.plan.redis_key)


def load_plan_from_manifest_record(record: Mapping[str, Any]) -> LoadedPlan:
    """Resolve and validate the persistent Plan referenced by a manifest row.

    The slug resolver necessarily returns a Redis key string at the external
    lookup boundary. After that, enqueue code keeps the Plan model instance and
    only asks for a raw key again when writing Redis-backed records or reports.
    """

    try:
        plan_slug = record["plan_slug"]
    except KeyError as exc:
        raise ValueError("manifest record missing required field: plan_slug") from exc

    resolved_key = SlugKeyResolver().resolve(plan_slug, expected_kind="plan")
    plan = Plan.load(resolved_key)
    step_count = _step_count(plan, plan_key=str(resolved_key))

    return LoadedPlan(
        slug=str(plan_slug),
        plan=plan,
        step_count=step_count,
    )


def _step_count(plan: Plan, *, plan_key: str) -> int:
    steps = plan.steps
    if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes, bytearray)):
        raise ValueError(f"plan steps must be a list: {plan_key}")

    count = len(steps)
    if count < 1:
        raise ValueError(f"plan has no steps: {plan_key}")
    return count


__all__ = ["LoadedPlan", "load_plan_from_manifest_record"]
