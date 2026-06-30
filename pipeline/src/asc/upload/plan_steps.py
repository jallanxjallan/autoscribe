import json
from collections.abc import Mapping, Sequence
from typing import Any

from asc.models.process.step import Step
from asc.redis.key import RedisKey
from asc.redis.primitives.keys import expire
from asc.state.slugmap import SlugKeyResolver

STEP_TTL_SECONDS = 60 * 60 * 24 * 7
INSTRUCTION_TTL_SECONDS = 60 * 60 * 24 * 30


def fanout_plan_steps(*, plan_identity: str, content: Mapping[str, Any]) -> tuple[str, ...]:
    """Materialize uploaded plan steps under the fresh plan identity.

    The plan itself is not stored. The slugmap points to ``plan:<identity>`` as a
    namespace pointer, and executable process state lives in
    ``step:<identity>:<index>`` records.
    """

    steps = content.get("steps")
    if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes, bytearray)):
        raise ValueError("plan record_content.steps must be a list")
    if not steps:
        raise ValueError("plan record_content.steps must not be empty")

    saved: list[str] = []
    for fallback_number, raw_step in enumerate(steps, start=1):
        if not isinstance(raw_step, Mapping):
            raise ValueError(f"plan step {fallback_number} must be an object")

        number = _step_number(raw_step, fallback=fallback_number)
        instruction_slugs = _string_list(raw_step.get("instruction_slugs", []), field=f"step {number} instruction_slugs")
        instruction_keys = _resolve_instruction_keys(instruction_slugs)
        _bump_instruction_ttls(instruction_keys)

        step = Step(**_step_payload(
            plan_identity=plan_identity,
            number=number,
            raw_step=raw_step,
            instruction_slugs=instruction_slugs,
            instruction_keys=instruction_keys,
        ))
        saved_key = step.save()
        expire_key(str(saved_key), STEP_TTL_SECONDS)
        saved.append(str(saved_key))

    return tuple(saved)


def expire_key(key: str, ttl_seconds: int) -> None:
    expire(RedisKey(key), int(ttl_seconds))


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


def _resolve_instruction_keys(instruction_slugs: Sequence[str]) -> list[str]:
    resolver = SlugKeyResolver()
    return [str(resolver.resolve(slug, expected_kind="instruction")) for slug in instruction_slugs]


def _bump_instruction_ttls(instruction_keys: Sequence[str]) -> None:
    for key in instruction_keys:
        expire_key(key, INSTRUCTION_TTL_SECONDS)


def _step_payload(
    *,
    plan_identity: str,
    number: int,
    raw_step: Mapping[str, Any],
    instruction_slugs: Sequence[str],
    instruction_keys: Sequence[str],
) -> dict[str, Any]:
    args = raw_step.get("args", {})
    if not isinstance(args, Mapping):
        raise ValueError(f"step {number} args must be an object")

    # The current Step model lives at asc.models.process.step. Recent versions
    # have used either:
    #   identity, step_number, engine, step_json
    # or:
    #   identity, step_number, engine, plus extra fields.
    # Build both shapes and filter only if the model is strict.
    step_json = dict(raw_step)
    step_json["instruction_slugs"] = list(instruction_slugs)
    step_json["instruction_keys"] = list(instruction_keys)

    candidate = {
        "identity": plan_identity,
        "step_number": number,
        "number": number,
        "engine": _required_string(raw_step.get("engine"), f"step {number} engine"),
        "step_json": step_json,
        "kind": str(raw_step.get("kind", "")),
        "label": str(raw_step.get("label", f"Step {number}")),
        "action": str(raw_step.get("action", raw_step.get("script", "execute_step"))),
        "instruction_slugs": list(instruction_slugs),
        "instruction_keys": list(instruction_keys),
        "script": str(raw_step.get("script", "")),
        "rag_profile": str(raw_step.get("rag_profile", "")),
        "args": dict(args),
        "args_json": json.dumps(dict(args), sort_keys=True),
    }

    fields = getattr(Step, "model_fields", None)
    config = getattr(Step, "model_config", {})
    allows_extra = isinstance(config, dict) and config.get("extra") == "allow"

    if isinstance(fields, Mapping) and not allows_extra:
        return {key: value for key, value in candidate.items() if key in fields}

    return candidate

def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


__all__ = [
    "INSTRUCTION_TTL_SECONDS",
    "STEP_TTL_SECONDS",
    "fanout_plan_steps",
]
