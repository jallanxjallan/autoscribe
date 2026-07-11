from collections.abc import Mapping, Sequence
from typing import Any

from asc.models.control.plan import Plan
from asc.models.control.step import Step
from asc.redis.key import RedisKey
from asc.registries.snapshot import build_registry_snapshot
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

    step_entries = plan_step_entries(plan.steps)
    if not step_entries:
        raise ValueError("plan steps must not be empty")

    plan.save(ttl=PLAN_TTL_SECONDS)

    registry = build_registry_snapshot()["registries"]
    saved: list[str] = []
    index_entries: dict[int, str] = {}

    for fallback_number, raw_step in step_entries:
        number = _step_number(raw_step, fallback=fallback_number)
        if number in index_entries:
            raise ValueError(f"duplicate plan step number: {number}")

        engine = plan.step_engine(number)
        engine_kind = _validate_registered_step(
            raw_step,
            number=number,
            engine=engine,
            registry=registry,
        )
        instruction_keys = _instruction_keys(raw_step, number=number)
        step = Step.from_plan(
            raw_step,
            identity=plan.identity,
            ordinal=number,
            engine=engine,
            engine_kind=engine_kind,
            instruction_keys=instruction_keys,
        )
        step_key = step.save(ttl=STEP_TTL_SECONDS)

        saved.append(step_key)
        index_entries[number] = step_key

    save_step_index(plan, index_entries)
    return tuple(saved)


def plan_step_entries(raw_steps: object) -> tuple[tuple[int, Mapping[str, Any]], ...]:
    """Return plan steps as sorted 1-based ``(fallback_number, step)`` pairs.

    Plan uploads used to carry ``steps`` as a list. The current client stores
    steps as a 1-based object keyed by display/index number. Ingest accepts
    both shapes, but enqueue never materializes upload records.
    """

    if isinstance(raw_steps, Mapping):
        entries: list[tuple[int, Mapping[str, Any]]] = []
        for raw_number, raw_step in raw_steps.items():
            number = _positive_int(raw_number, field="plan step key")
            if not isinstance(raw_step, Mapping):
                raise ValueError(f"plan step {number} must be an object")
            entries.append((number, raw_step))
        return tuple(sorted(entries, key=lambda item: item[0]))

    if isinstance(raw_steps, Sequence) and not isinstance(raw_steps, (str, bytes, bytearray)):
        entries = []
        for number, raw_step in enumerate(raw_steps, start=1):
            if not isinstance(raw_step, Mapping):
                raise ValueError(f"plan step {number} must be an object")
            entries.append((number, raw_step))
        return tuple(entries)

    return ()


def save_step_index(plan: Plan, entries: Mapping[int | str, str]) -> str:
    if not entries:
        raise ValueError("plan index must not be empty")

    key = RedisKey(kind=Plan.kind, identity=plan.identity, suffix="index")
    key.hset(mapping={str(number): step_key for number, step_key in entries.items()})
    key.expire(PLAN_TTL_SECONDS)
    return key.raw_key



def _validate_registered_step(
    raw_step: Mapping[str, Any],
    *,
    number: int,
    engine: str,
    registry: Mapping[str, Any],
) -> str:
    engines = registry.get("engines", {})
    if not isinstance(engines, Mapping) or engine not in engines:
        raise ValueError(f"step {number} engine is not registered: {engine!r}")

    engine_record = engines[engine]
    if not isinstance(engine_record, Mapping):
        raise ValueError(f"step {number} engine registry record is invalid: {engine!r}")

    engine_kind = str(engine_record.get("kind", "")).strip()
    declared_kind = str(raw_step.get("kind", raw_step.get("engine_kind", ""))).strip()
    if declared_kind and declared_kind != engine_kind:
        raise ValueError(
            f"step {number} kind does not match engine {engine!r}: "
            f"declared={declared_kind!r} registered={engine_kind!r}"
        )

    if engine_kind == "llm":
        model = str(raw_step.get("model", "")).strip()
        model_key = f"{engine}.{model}"
        models = registry.get("models", {})
        if not model:
            raise ValueError(f"step {number} LLM model must not be empty")
        if not isinstance(models, Mapping) or model_key not in models:
            raise ValueError(
                f"step {number} model is not registered for {engine!r}: {model!r}"
            )

    elif engine_kind == "script":
        script = str(raw_step.get("script", "")).strip()
        scripts = registry.get("local_scripts", {})
        if not script:
            raise ValueError(f"step {number} script must not be empty")
        if not isinstance(scripts, Mapping) or script not in scripts:
            raise ValueError(f"step {number} script is not registered: {script!r}")

    elif engine_kind == "rag":
        profile = str(raw_step.get("rag_profile", "")).strip()
        profiles = registry.get("rag_profiles", {})
        if not profile:
            raise ValueError(f"step {number} RAG profile must not be empty")
        if not isinstance(profiles, Mapping) or profile not in profiles:
            raise ValueError(f"step {number} RAG profile is not registered: {profile!r}")

    else:
        raise ValueError(f"step {number} engine has unsupported kind: {engine_kind!r}")

    return engine_kind

def _instruction_keys(raw_step: Mapping[str, Any], *, number: int) -> list[str]:
    slugs = _string_list(
        raw_step.get("instruction_slugs", []),
        field=f"step {number} instruction_slugs",
    )
    resolver = SlugKeyResolver()
    keys = [str(resolver.resolve(slug, expected_kind="instruction")) for slug in slugs]
    for key in keys:
        RedisKey(key).expire(INSTRUCTION_TTL_SECONDS)
    return keys


def _step_number(raw_step: Mapping[str, Any], *, fallback: int) -> int:
    value = raw_step.get("number", raw_step.get("index", fallback))
    return _positive_int(value, field="step number")


def _positive_int(value: object, *, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer: {value!r}")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer: {value!r}") from exc
    if number < 1:
        raise ValueError(f"{field} must be positive: {number}")
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
    "plan_step_entries",
    "save_step_index",
]
