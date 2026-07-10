"""Build the fully hydrated input for one engine call."""

from __future__ import annotations

from dataclasses import dataclass

from asc.models.control.instruction import Instruction
from asc.models.control.step import Step
from asc.models.process.call import CallRecord
from asc.models.process.result import Response, Retrieval, Transform
from asc.redis.key import RedisKey


ContentSource = CallRecord | Response | Transform | Retrieval

_SOURCE_MODELS: dict[str, type[ContentSource]] = {
    "call": CallRecord,
    "response": Response,
    "transform": Transform,
    "retrieval": Retrieval,
}


@dataclass(frozen=True, slots=True)
class EngineInput:
    """Validated, fully hydrated context passed across the engine boundary."""

    call: CallRecord
    source: ContentSource
    step: Step
    instructions: tuple[Instruction, ...]
    content: str


def build_engine_input(
    *,
    data_key: str,
    step: Step,
) -> EngineInput:
    """Load all persisted models needed to execute one step."""
    source = load_content_source(data_key)
    call = load_source_call(data_key)
    instructions = load_instructions(step.instruction_keys)

    if source.identity != call.identity:
        raise ValueError(
            "runtime source identity does not match call identity: "
            f"source={source.identity!r} call={call.identity!r}"
        )

    return EngineInput(
        call=call,
        source=source,
        step=step,
        instructions=instructions,
        content=source.content,
    )


def load_content_source(key: str) -> ContentSource:
    """Load the canonical content-bearing model addressed by key."""
    if not isinstance(key, str) or not key.strip():
        raise ValueError("worker data key must be non-empty")

    redis_key = RedisKey(key.strip())

    try:
        model = _SOURCE_MODELS[redis_key.kind]
    except KeyError as exc:
        supported = ", ".join(sorted(_SOURCE_MODELS))
        raise ValueError(
            f"unsupported worker data kind {redis_key.kind!r}: "
            f"{redis_key.raw_key!r}; expected one of {supported}"
        ) from exc

    return model.load(redis_key)


def load_source_call(data_key: str) -> CallRecord:
    """Load the original call sharing the runtime source identity."""
    source_key = RedisKey(data_key)
    call_key = RedisKey(
        kind="call",
        identity=source_key.identity,
        suffix="record",
    )
    return CallRecord.load(call_key)


def load_instructions(
    instruction_keys: list[str],
) -> tuple[Instruction, ...]:
    """Hydrate the instructions referenced by a Step, preserving order."""
    return tuple(Instruction.load(key) for key in instruction_keys)


__all__ = [
    "ContentSource",
    "EngineInput",
    "build_engine_input",
    "load_content_source",
    "load_instructions",
    "load_source_call",
]
