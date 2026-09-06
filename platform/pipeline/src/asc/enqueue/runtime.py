"""Materialize ephemeral call-scoped runtime steps."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from asc.enqueue.instruction import resolve_instruction_key
from asc.models.control.instruction import Instruction
from asc.control.repository import ControlRepository, GitInstruction
from asc.enqueue.plan import resolve_components
from asc.models.process.runtime import Runtime

RUNTIME_TTL_SECONDS = 60 * 60 * 24
DIRECTIVE_TTL_SECONDS = 60 * 60


def materialize_runtimes(
    *,
    call_identity: str,
    plan: Any,
    control_revision: str,
    directive: str | None = None,
    instruction_sources: dict[str, GitInstruction] | None = None,
) -> tuple[Runtime, ...]:
    """Compile and save every embedded plan step for one call.

    A leading file directive, when present, is persisted as a short-lived
    instruction and attached only to runtime step 1 under the ``directive``
    instruction label.

    All runtime records are written before the caller exposes the call through
    the active zset. No runtime index is created; keys are deterministic from
    call identity and ordinal.
    """

    if instruction_sources is None:
        instruction_sources = resolve_components(
            plan, ControlRepository.at_revision(control_revision)
        )
    runtimes: list[Runtime] = []
    directive_instruction: Instruction | None = None
    instruction_cache: dict[str, str] = {}
    total_steps = plan.total_steps
    try:
        if directive:
            directive_instruction = _save_directive_instruction(
                call_identity=call_identity,
                content=directive,
            )

        for ordinal in range(1, total_steps + 1):
            step = plan.step_definition(ordinal)
            args = dict(step["args"])
            engine = step["engine"]
            engine_kind = step["engine_kind"]
            instruction_keys = _resolve_instruction_keys(
                step,
                instruction_cache=instruction_cache,
                control_revision=control_revision,
                instruction_sources=instruction_sources,
            )
            if ordinal == 1 and directive_instruction is not None:
                instruction_keys["directive"] = directive_instruction.raw_key

            payload: dict[str, Any] = {
                **step,
                "identity": call_identity,
                "plan_identity": str(plan.identity),
                "ordinal": ordinal,
                "total_steps": total_steps,
                "engine": engine,
                "engine_kind": engine_kind,
                "instruction_keys": instruction_keys,
                "args": args,
            }
            payload.pop("instructions", None)

            # Control is already authored; Redis deserialization keeps its own parser.
            runtime = Runtime.model_construct(**payload)
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

    instruction = Instruction(
        identity=call_identity, title="Call directive", content=content
    )
    instruction.save(ttl=DIRECTIVE_TTL_SECONDS)
    return instruction


def _resolve_instruction_keys(
    step: Mapping[str, Any],
    *,
    control_revision: str,
    instruction_cache: dict[str, str] | None = None,
    instruction_sources: dict[str, GitInstruction] | None = None,
) -> dict[str, list[str]]:
    references = step["instructions"]
    cache = instruction_cache if instruction_cache is not None else {}
    resolved = {}
    for scope, identities in references.items():
        if not identities:
            continue
        keys = []
        for identity in identities:
            if identity not in cache:
                cache[identity] = resolve_instruction_key(
                    identity,
                    control_revision=control_revision,
                    **(
                        {"source": instruction_sources[identity]}
                        if instruction_sources is not None
                        else {}
                    ),
                )
            keys.append(cache[identity])
        resolved[scope] = keys
    return resolved
