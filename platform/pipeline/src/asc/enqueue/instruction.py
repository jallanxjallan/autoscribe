"""Versioned instruction materialization from an explicitly pinned Control commit."""

import hashlib
import json

from asc.config.runtime import (
    INSTRUCTION_TTL_SECONDS,
    MIN_REMAINING_INSTRUCTION_TTL_SECONDS,
)
from asc.control.repository import GitInstruction, read_instruction
from asc.models.control.instruction import Instruction
from asc.redis.key import RedisKey
from asc.state.instruction_materializations import InstructionMaterializations


def resolve_instruction_key(
    instruction_identity: str,
    *,
    control_revision: str,
    source: GitInstruction | None = None,
) -> str:
    source = (
        source
        if source is not None
        else read_instruction(instruction_identity, control_revision)
    )
    materializations = InstructionMaterializations()
    current_key = materializations.get(source.identity)
    if current_key and _can_reuse(current_key, source):
        return current_key
    return _materialize(source, materializations=materializations)


def _can_reuse(key_value: str, source: GitInstruction) -> bool:
    try:
        key = RedisKey(key_value)
        if key.kind != Instruction.kind or key.suffix != Instruction.component:
            return False
        if key.ttl() < MIN_REMAINING_INSTRUCTION_TTL_SECONDS:
            return False
        instruction = Instruction.load(key)
        return (
            instruction.control_identity == source.identity
            and instruction.source_fingerprint == source.fingerprint
        )
    except (RuntimeError, TypeError, ValueError):
        return False


def _materialize(
    source: GitInstruction, *, materializations: InstructionMaterializations
) -> str:
    instruction = Instruction.model_construct(
        control_identity=source.identity,
        source_fingerprint=source.fingerprint,
        title=source.title,
        content=source.content,
        content_sha256=hashlib.sha256(source.content.encode("utf-8")).hexdigest(),
        extra_json=json.dumps(source.extra),
    )
    new_key = str(instruction.save(ttl=INSTRUCTION_TTL_SECONDS))
    materializations.set(source.identity, new_key)
    return new_key
