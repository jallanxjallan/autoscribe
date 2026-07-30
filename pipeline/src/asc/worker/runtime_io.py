"""Hydrate one canonical runtime record for engine execution."""

from __future__ import annotations

from dataclasses import dataclass

from asc.models.control.instruction import Instruction
from asc.models.process.call import CallRecord
from asc.models.process.result import Response
from asc.models.process.runtime import Runtime
from asc.redis.key import RedisKey


ContentSource = CallRecord | Response


@dataclass(frozen=True, slots=True)
class EngineInput:
    """Persisted runtime plus the content and instructions it addresses."""

    runtime: Runtime
    call: CallRecord
    source: ContentSource
    instructions: tuple[Instruction, ...]
    content: str


def build_engine_input(runtime: Runtime) -> EngineInput:
    """Hydrate the records referenced by one validated Runtime."""
    call = _load_call(runtime)
    source = _load_source(runtime=runtime, call=call)
    instructions = load_instructions(runtime.instruction_keys)

    return EngineInput(
        runtime=runtime,
        call=call,
        source=source,
        instructions=instructions,
        content=source.content,
    )


def _load_call(runtime: Runtime) -> CallRecord:
    call_key = RedisKey(kind="call", identity=runtime.identity, suffix="record")
    return CallRecord.load(call_key)


def _load_source(*, runtime: Runtime, call: CallRecord) -> ContentSource:
    if runtime.ordinal == 1:
        return call

    response_key = RedisKey(
        kind="response",
        identity=runtime.identity,
        suffix=str(runtime.ordinal - 1),
    )
    response = Response.load(response_key)
    if response.identity != runtime.identity:
        raise ValueError(
            "runtime source response identity does not match runtime identity: "
            f"response={response.identity!r} runtime={runtime.identity!r}"
        )
    return response


def load_instructions(
    instruction_keys: dict[str, str | list[str]],
) -> tuple[Instruction, ...]:
    """Hydrate instructions in their canonical labeled order."""
    preferred = ("role", "context", "instructions")
    ordered_labels = [label for label in preferred if label in instruction_keys]
    ordered_labels.extend(
        label for label in instruction_keys if label not in preferred
    )
    ordered_keys: list[str] = []
    for label in ordered_labels:
        keys = instruction_keys[label]
        ordered_keys.extend(keys if isinstance(keys, list) else [keys])
    return tuple(Instruction.load(key) for key in ordered_keys)


__all__ = [
    "ContentSource",
    "EngineInput",
    "build_engine_input",
    "load_instructions",
]
