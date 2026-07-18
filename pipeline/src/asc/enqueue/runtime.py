"""Materialize ephemeral call-scoped runtime steps."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from asc.models.process.runtime import Runtime
from asc.state.slugmap import SlugMap

RUNTIME_TTL_SECONDS = 60 * 60 * 24
INSTRUCTION_ORDER = ("role", "context", "instructions")


def materialize_runtimes(*, call_identity: str, plan: Any) -> tuple[Runtime, ...]:
    """Compile and save every embedded plan step for one call.

    All runtime records are written before the caller exposes the call through
    the active zset. No runtime index is created; keys are deterministic from
    call identity and ordinal.
    """

    runtimes: list[Runtime] = []
    total_steps = plan.total_steps
    try:
        for ordinal in range(1, total_steps + 1):
            step = plan.step_definition(ordinal)
            args = _step_args(step, ordinal=ordinal)
            engine = _engine(step, args=args, ordinal=ordinal)
            engine_kind = _engine_kind(step, args=args, ordinal=ordinal)
            instruction_keys = _resolve_instruction_keys(step, ordinal=ordinal)

            payload: dict[str, Any] = {
                **step,
                **args,
                "identity": call_identity,
                "plan_identity": str(plan.identity),
                "ordinal": ordinal,
                "total_steps": total_steps,
                "engine": engine,
                "engine_kind": engine_kind,
                "instruction_keys": instruction_keys,
                "args": args,
            }
            payload.pop("instruction", None)
            payload.pop("instruction_slugs", None)
            payload.pop("instructions", None)

            runtime = Runtime.model_validate(payload)
            runtime.save(ttl=RUNTIME_TTL_SECONDS)
            runtimes.append(runtime)
    except Exception:
        for runtime in runtimes:
            runtime.delete()
        raise

    return tuple(runtimes)


def _step_args(step: Mapping[str, Any], *, ordinal: int) -> dict[str, Any]:
    value = step.get("args", {})
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"plan step {ordinal} args must be an object")
    return dict(value)


def _engine(step: Mapping[str, Any], *, args: Mapping[str, Any], ordinal: int) -> str:
    value = step.get("engine", args.get("engine"))
    if isinstance(value, Mapping):
        value = value.get("key") or value.get("module")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"plan step {ordinal} must provide an engine")
    return value.strip()


def _engine_kind(step: Mapping[str, Any], *, args: Mapping[str, Any], ordinal: int) -> str:
    value = step.get("engine_kind", step.get("kind", args.get("engine_kind")))
    if not isinstance(value, str) or value.strip() not in {"llm", "script", "rag"}:
        raise ValueError(f"plan step {ordinal} must provide engine_kind llm, script, or rag")
    return value.strip()


def _resolve_instruction_keys(step: Mapping[str, Any], *, ordinal: int) -> dict[str, str]:
    raw = step.get("instruction_slugs", step.get("instructions"))
    if raw in (None, ""):
        instruction = step.get("instruction")
        raw = {} if instruction in (None, "") else {"instructions": instruction}
    if raw in (None, ""):
        return {}
    if isinstance(raw, list):
        if len(raw) > len(INSTRUCTION_ORDER):
            raise ValueError(f"plan step {ordinal} has too many legacy instruction references")
        raw = {INSTRUCTION_ORDER[index]: value for index, value in enumerate(raw)}
    if not isinstance(raw, Mapping):
        raise ValueError(f"plan step {ordinal} instruction references must be a labeled object")

    resolver = SlugMap()
    resolved: dict[str, str] = {}
    for label in INSTRUCTION_ORDER:
        reference = raw.get(label)
        if reference in (None, ""):
            continue
        if not isinstance(reference, str):
            raise ValueError(f"plan step {ordinal} instruction {label} must be a string")
        resolved[label] = resolver.resolve(reference.strip(), expected_kind="instruction")

    unknown = set(raw) - set(INSTRUCTION_ORDER)
    if unknown:
        raise ValueError(
            f"plan step {ordinal} has unsupported instruction labels: {', '.join(sorted(map(str, unknown)))}"
        )
    return resolved


__all__ = [
    "INSTRUCTION_ORDER",
    "RUNTIME_TTL_SECONDS",
    "materialize_runtimes",
]
