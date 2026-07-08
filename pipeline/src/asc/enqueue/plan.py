from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any

from asc.redis.key import RedisKey
from asc.redis.primitives.hashes import hgetall
from asc.state.slugmap import SlugMap


@dataclass(frozen=True, slots=True)
class LoadedPlan:
    """Resolved uploaded-plan record plus its materialized plan index."""

    slug: str
    plan_key: str
    plan_index_key: str
    plan_index: dict[str, str]

    @property
    def raw_key(self) -> str:
        return self.plan_key

    @property
    def step_count(self) -> int:
        return len(self.plan_index)


def load_plan_from_manifest_record(record: Mapping[str, Any]) -> LoadedPlan:
    """Resolve the top-level record_plan field emitted by dispatch-run.

    Plan upload owns materialization of reusable Step records and writes the
    reusable ``plan:<plan_identity>:index`` hash. Enqueue only resolves the
    plan slug and reads that uploaded plan index so runtime can clone it into
    the call index.
    """

    try:
        plan_slug = record["record_plan"]
    except KeyError as exc:
        raise ValueError("enqueue record missing required field: record_plan") from exc

    if not isinstance(plan_slug, str) or not plan_slug.strip():
        raise ValueError("record_plan must be a non-empty string")

    clean_slug = plan_slug.strip()
    resolved_key = resolve_plan_record_key(clean_slug)
    index_key = plan_index_key(resolved_key)
    index = load_plan_index(index_key)

    return LoadedPlan(
        slug=clean_slug,
        plan_key=resolved_key,
        plan_index_key=index_key,
        plan_index=index,
    )


def resolve_plan_record_key(plan_slug: str) -> str:
    """Resolve a plan slug to the uploaded ``plan:<identity>:record`` key."""

    resolved_key = SlugMap().get(plan_slug)
    if not resolved_key:
        raise KeyError(f"missing slugmap entry for plan: {plan_slug}")

    key = RedisKey(str(resolved_key))
    if key.kind != "plan":
        raise ValueError(f"record_plan resolved to non-plan key: {resolved_key}")

    if key.suffix in (None, "", "record"):
        return str(RedisKey(kind="plan", identity=key.identity, suffix="record"))

    raise ValueError(f"record_plan resolved to non-plan record key: {resolved_key}")


def plan_index_key(plan_record_key: str) -> str:
    key = RedisKey(plan_record_key)
    if key.kind != "plan" or key.suffix != "record":
        raise ValueError(f"resolved plan key must be plan:<identity>:record: {plan_record_key}")

    return str(RedisKey(kind="plan", identity=key.identity, suffix="index"))


def load_plan_index(index_key: str) -> dict[str, str]:
    """Load the already-materialized plan index hash."""

    raw_index = hgetall(RedisKey(index_key))
    if not raw_index:
        raise ValueError(f"plan index is empty or missing: {index_key}")

    index = {_text(slot): _text(value) for slot, value in raw_index.items()}
    _validate_plan_index(index_key=index_key, index=index)
    return index


def _text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


def _validate_plan_index(*, index_key: str, index: Mapping[str, str]) -> None:
    for slot, step_key in index.items():
        if not slot:
            raise ValueError(f"plan index contains an empty slot: {index_key}")
        if slot == "0":
            raise ValueError(f"plan index must not contain call slot 0: {index_key}")

        step = RedisKey(step_key)
        if step.kind != "step":
            raise ValueError(f"plan index value is not a step key: {index_key}[{slot}]={step_key}")


__all__ = [
    "LoadedPlan",
    "load_plan_from_manifest_record",
    "load_plan_index",
    "plan_index_key",
    "resolve_plan_record_key",
]
