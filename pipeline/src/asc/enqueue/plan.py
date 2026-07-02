from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from asc.models.control.plan import Plan
from asc.models.control.step import Step
from asc.redis.key import RedisKey
from asc.state.slugmap import SlugMap


@dataclass(frozen=True, slots=True)
class LoadedPlan:
    """Resolved uploaded plan record plus its materialized reusable step index."""

    slug: str
    record_key: RedisKey
    index_key: RedisKey
    index: dict[str, str]

    @property
    def raw_key(self) -> str:
        return self.record_key.raw_key

    @property
    def step_count(self) -> int:
        return len(self.index)


def load_plan_for_record(record: Mapping[str, Any]) -> LoadedPlan:
    """Resolve the dispatch record's public plan slug to the saved plan identity."""

    plan_slug = _required_string(record.get("record_plan"), field="record_plan")
    record_key = _resolve_plan_record_key(plan_slug)
    index_key = RedisKey(kind=Plan.kind, identity=record_key.identity, suffix="index")
    index = _load_plan_index(index_key)

    return LoadedPlan(
        slug=plan_slug,
        record_key=record_key,
        index_key=index_key,
        index=index,
    )


def _resolve_plan_record_key(plan_slug: str) -> RedisKey:
    resolved = SlugMap().get(plan_slug)
    if not resolved:
        raise KeyError(f"missing slugmap entry for plan: {plan_slug}")

    key = RedisKey(str(resolved))
    if key.kind != Plan.kind or key.suffix != Plan.suffix:
        raise ValueError(f"record_plan resolved to non-plan record key: {resolved}")

    return key


def _load_plan_index(index_key: RedisKey) -> dict[str, str]:
    raw_index = index_key.hgetall()
    if not raw_index:
        raise ValueError(f"plan index is empty or missing: {index_key.raw_key}")

    index = {_text(slot): _text(step_key) for slot, step_key in raw_index.items()}
    _validate_plan_index(index_key=index_key, index=index)
    return index


def _validate_plan_index(*, index_key: RedisKey, index: Mapping[str, str]) -> None:
    for slot, step_key in index.items():
        if not slot:
            raise ValueError(f"plan index contains an empty slot: {index_key.raw_key}")
        if slot == "0":
            raise ValueError(f"plan index must not contain call slot 0: {index_key.raw_key}")

        step = RedisKey(step_key)
        if step.kind != Step.kind:
            raise ValueError(
                f"plan index value is not a step key: {index_key.raw_key}[{slot}]={step_key}"
            )


def _required_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"enqueue record {field} must be a non-empty string")
    return value.strip()


def _text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


__all__ = ["LoadedPlan", "load_plan_for_record"]
