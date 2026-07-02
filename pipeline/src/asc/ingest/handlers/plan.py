import json
from collections.abc import Mapping, Sequence
from typing import Any

from asc.models.control.plan import Plan
from asc.models.control.step import Step
from asc.redis.key import RedisKey
from asc.state.slugmap import SlugKeyResolver, SlugMap
from asc.ingest.common import IngestedItem
from asc.ingest.expiry import expire_old_key

STEP_TTL_SECONDS = 60 * 60 * 24 * 7
PLAN_TTL_SECONDS = 60 * 60 * 24 * 30
INSTRUCTION_TTL_SECONDS = 60 * 60 * 24 * 30


def ingest_plan(record: Mapping[str, Any]) -> IngestedItem:
    """Validate, save, index, and publish a plan upload envelope."""

    plan = Plan.model_validate(record)
    step_keys = fanout_steps(plan)

    slugmap = SlugMap()
    old_key = slugmap.get(plan.slug)
    new_key = str(plan.redis_key)

    slugmap.set(plan.slug, new_key)
    expire_old_key(old_key, new_key)

    if not step_keys:
        raise ValueError("plan steps must not be empty")

    return IngestedItem(record_type="plan", slug=plan.slug, key=new_key)


def fanout_steps(plan: Plan) -> tuple[str, ...]:
    """Save a Plan and materialize its executable Step records."""

    if not plan.steps:
        raise ValueError("plan steps must not be empty")

    plan.save(ttl=PLAN_TTL_SECONDS)

    saved: list[str] = []
    index_entries: dict[int, str] = {}

    for fallback_number, raw_step in enumerate(plan.steps, start=1):
        number = _step_number(raw_step, fallback=fallback_number)
        if number in index_entries:
            raise ValueError(f"duplicate plan step number: {number}")

        instruction_keys = _instruction_keys(raw_step, number=number)
        step = Step(**_step_payload(plan=plan, number=number, raw_step=raw_step, instruction_keys=instruction_keys))
        step_key = step.save(ttl=STEP_TTL_SECONDS)

        saved.append(step_key)
        index_entries[number] = step_key

    save_step_index(plan, index_entries)
    return tuple(saved)


def save_step_index(plan: Plan, entries: Mapping[int | str, str]) -> str:
    if not entries:
        raise ValueError("plan index must not be empty")

    key = RedisKey(kind=Plan.kind, identity=plan.identity, suffix="index")
    key.hset(mapping={str(number): step_key for number, step_key in entries.items()})
    key.expire(PLAN_TTL_SECONDS)
    return key.raw_key


def _step_payload(
    *,
    plan: Plan,
    number: int,
    raw_step: Mapping[str, Any],
    instruction_keys: Sequence[str],
) -> dict[str, Any]:
    args = raw_step.get("args", {})
    if not isinstance(args, Mapping):
        raise ValueError(f"step {number} args must be an object")

    return {
        "identity": plan.identity,
        "step_number": number,
        "engine": plan.step_engine(number),
        "instruction_keys": list(instruction_keys),
        "script": str(raw_step.get("script", "")),
        "rag_profile": str(raw_step.get("rag_profile", "")),
        "args_json": json.dumps(dict(args), ensure_ascii=False, sort_keys=True),
    }


def _instruction_keys(raw_step: Mapping[str, Any], *, number: int) -> list[str]:
    slugs = _string_list(raw_step.get("instruction_slugs", []), field=f"step {number} instruction_slugs")
    resolver = SlugKeyResolver()
    keys = [str(resolver.resolve(slug, expected_kind="instruction")) for slug in slugs]
    for key in keys:
        RedisKey(key).expire(INSTRUCTION_TTL_SECONDS)
    return keys


def _step_number(raw_step: Mapping[str, Any], *, fallback: int) -> int:
    value = raw_step.get("number", raw_step.get("index", fallback))
    if isinstance(value, bool):
        raise ValueError(f"step number must be an integer: {value!r}")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"step number must be an integer: {value!r}") from exc
    if number < 1:
        raise ValueError(f"step number must be positive: {number}")
    return number


def _string_list(value: object, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field} must be a list of strings")

    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} must be a list of non-empty strings")
        result.append(item.strip())
    return result


__all__ = [
    "INSTRUCTION_TTL_SECONDS",
    "PLAN_TTL_SECONDS",
    "STEP_TTL_SECONDS",
    "fanout_steps",
    "ingest_plan",
    "save_step_index",
]
