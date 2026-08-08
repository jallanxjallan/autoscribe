"""Materialize ephemeral call-scoped runtime steps."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from asc.models.control.instruction import Instruction
from asc.models.process.runtime import Runtime
from asc.state.slugmap import SlugMap

RUNTIME_TTL_SECONDS = 60 * 60 * 24
DIRECTIVE_TTL_SECONDS = 60 * 60
INSTRUCTION_ORDER = ("standing", "role", "context", "task", "directive")


def materialize_runtimes(
    *,
    call_identity: str,
    plan: Any,
    directive: str | None = None,
) -> tuple[Runtime, ...]:
    """Compile and save every embedded plan step for one call.

    A leading file directive, when present, is persisted as a short-lived
    instruction and attached only to runtime step 1 under the ``directive``
    instruction label.

    All runtime records are written before the caller exposes the call through
    the active zset. No runtime index is created; keys are deterministic from
    call identity and ordinal.
    """

    runtimes: list[Runtime] = []
    directive_instruction: Instruction | None = None
    total_steps = plan.total_steps
    try:
        if directive:
            directive_instruction = _save_directive_instruction(
                call_identity=call_identity,
                content=directive,
            )

        for ordinal in range(1, total_steps + 1):
            step = plan.step_definition(ordinal)
            args = _step_args(step, ordinal=ordinal)
            engine = _engine(step, args=args, ordinal=ordinal)
            engine_kind = _engine_kind(step, args=args, ordinal=ordinal)
            instruction_keys = _resolve_instruction_keys(
                step, ordinal=ordinal
            )
            if ordinal == 1 and directive_instruction is not None:
                instruction_keys["directive"] = directive_instruction.raw_key

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
        if directive_instruction is not None:
            directive_instruction.delete()
        raise

    return tuple(runtimes)


def delete_ephemeral_instructions(runtimes: tuple[Runtime, ...]) -> None:
    """Delete call-scoped directive instructions during enqueue rollback."""

    if not runtimes:
        return
    key = runtimes[0].instruction_keys.get("directive")
    if not key:
        return
    Instruction.load(key).delete()


def _save_directive_instruction(*, call_identity: str, content: str) -> Instruction:
    """Persist the call-scoped directive using the call identity."""

    instruction = Instruction(identity=call_identity, content=content)
    instruction.save(ttl=DIRECTIVE_TTL_SECONDS)
    return instruction


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
    if isinstance(value, str) and value.strip():
        return value.strip()

    kind = step.get("engine_kind", step.get("kind", args.get("engine_kind")))
    if isinstance(kind, str) and kind.strip() == "script":
        return "engines.local"

    raise ValueError(f"plan step {ordinal} must provide an engine")


def _engine_kind(step: Mapping[str, Any], *, args: Mapping[str, Any], ordinal: int) -> str:
    value = step.get("engine_kind", step.get("kind", args.get("engine_kind")))
    if not isinstance(value, str) or value.strip() not in {"llm", "script", "rag"}:
        raise ValueError(f"plan step {ordinal} must provide engine_kind llm, script, or rag")
    return value.strip()


def _resolve_instruction_keys(
    step: Mapping[str, Any],
    *,
    ordinal: int,
) -> dict[str, str | list[str]]:
    raw = step.get("instruction_slugs", step.get("instructions"))
    if raw in (None, ""):
        instruction = step.get("instruction")
        raw = {} if instruction in (None, "") else {"task": instruction}
    if raw in (None, ""):
        return {}
    if isinstance(raw, list):
        if len(raw) > 4:
            raise ValueError(f"plan step {ordinal} has too many legacy instruction references")
        # Historical positional order was role, context, specifics, instructions.
        # Both former bottom-of-stack slots now normalize to task.
        raw = {
            "role": raw[0] if len(raw) > 0 else None,
            "context": raw[1] if len(raw) > 1 else None,
            "task": [value for value in raw[2:4] if value not in (None, "", [])],
        }
    if not isinstance(raw, Mapping):
        raise ValueError(f"plan step {ordinal} instruction references must be a labeled object")

    resolved: dict[str, str | list[str]] = {}
    for label in INSTRUCTION_ORDER[:-1]:
        reference = raw.get(label)
        if reference in (None, "", []):
            continue

        references: list[str]
        was_list = isinstance(reference, list)
        if isinstance(reference, str):
            references = [reference]
        elif was_list and all(isinstance(item, str) for item in reference):
            references = reference
        else:
            raise ValueError(
                f"plan step {ordinal} instruction {label} must be a string "
                "or a list of strings"
            )

        clean = [item.strip() for item in references]
        if any(not item for item in clean):
            raise ValueError(
                f"plan step {ordinal} instruction {label} contains an empty slug"
            )

        slugmap = SlugMap()
        keys = [slugmap.resolve(item, expected_kind="instruction") for item in clean]
        # Preserve the representation supplied by the plan. Older plans and
        # consumers continue to receive one key as a string; current plans can
        # carry an ordered list of keys under any instruction label.
        resolved[label] = keys if was_list else keys[0]

    unknown = set(raw) - set(INSTRUCTION_ORDER[:-1])
    if unknown:
        raise ValueError(
            f"plan step {ordinal} has unsupported instruction labels: {', '.join(sorted(map(str, unknown)))}"
        )
    return resolved


__all__ = [
    "DIRECTIVE_TTL_SECONDS",
    "INSTRUCTION_ORDER",
    "RUNTIME_TTL_SECONDS",
    "delete_ephemeral_instructions",
    "materialize_runtimes",
]
