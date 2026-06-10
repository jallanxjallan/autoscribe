from __future__ import annotations

from typing import Any

from asc.orchestrator.errors import OrchestratorContractError
from asc.orchestrator.queues import enqueue_worker
from asc.orchestrator.state import (
    current_step_number,
    plan_key,
    save_call_state,
    set_current_step_number,
)
from asc.orchestrator.verify import verify_input_artifact


def advance_call_state(call_state: Any, call_state_key: str) -> bool:
    """Advance call_state to the next plan step and enqueue worker custody.

    Returns False when the just-finished step was terminal.
    """

    next_step = current_step_number(call_state) + 1
    if not plan_step_exists(plan_key(call_state), next_step):
        return False

    set_current_step_number(call_state, next_step)
    verify_input_artifact(call_state)
    save_call_state(call_state)
    enqueue_worker(call_state_key)
    return True


def plan_step_exists(plan_identifier: str, step_number: int) -> bool:
    """Return whether the immutable uploaded plan contains step_number."""

    plan = _load_plan(plan_identifier)
    for attr_name in ("steps", "plan_steps"):
        steps = getattr(plan, attr_name, None)
        if steps is None:
            continue
        for step in steps:
            value = getattr(step, "step_number", None)
            if value is None:
                value = getattr(step, "number", None)
            if value is None and isinstance(step, dict):
                value = step.get("step_number", step.get("number"))
            if value is not None and int(value) == int(step_number):
                return True
        return False

    for method_name in ("has_step", "contains_step"):
        method = getattr(plan, method_name, None)
        if callable(method):
            return bool(method(step_number))

    raise OrchestratorContractError(
        f"cannot determine whether plan {plan_identifier!r} has step {step_number}"
    )


def _load_plan(plan_identifier: str) -> Any:
    try:
        from asc.models.control.plan import PlanRecord
    except ModuleNotFoundError:
        try:
            from asc.models.plan import PlanRecord
        except ModuleNotFoundError as exc:
            raise OrchestratorContractError("no PlanRecord model available") from exc

    for method_name in ("load_from_key", "load", "from_key"):
        method = getattr(PlanRecord, method_name, None)
        if callable(method):
            return method(plan_identifier)

    try:
        from asc.redis.key import RedisKey
    except ModuleNotFoundError as exc:
        raise OrchestratorContractError("PlanRecord has no load method") from exc

    return RedisKey(plan_identifier).load_model(PlanRecord)  # type: ignore[attr-defined]
