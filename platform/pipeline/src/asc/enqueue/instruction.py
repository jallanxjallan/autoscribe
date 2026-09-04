"""Lazy instruction materialization for the enqueue boundary."""

from __future__ import annotations

import hashlib

import ulid

from asc.config.runtime import (
    INSTRUCTION_TTL_SECONDS,
    MIN_REMAINING_INSTRUCTION_TTL_SECONDS,
)
from asc.control.repository import GitInstruction, read_instruction
from asc.models.control.instruction import Instruction
from asc.redis.key import RedisKey
from asc.state.slugmap import SlugMap


def resolve_instruction_key(instruction_slug: str) -> str:
    """Return a safe current materialization for one Git instruction slug."""
    source = read_instruction(instruction_slug)
    slugmap = SlugMap()
    current_key = slugmap.get(source.slug)
    if current_key and _can_reuse(current_key, source):
        return current_key
    return _materialize(source, slugmap=slugmap)


def _can_reuse(key_value: str, source: GitInstruction) -> bool:
    try:
        key = RedisKey(key_value)
        if key.kind != Instruction.kind or key.suffix != Instruction.component:
            return False
        materialized_at = float(ulid.ULID.from_str(key.identity).timestamp)
        if materialized_at <= source.commit_timestamp:
            return False
        if key.ttl() < MIN_REMAINING_INSTRUCTION_TTL_SECONDS:
            return False
        instruction = Instruction.load(key)
        if instruction.slug != source.slug:
            return False
        return True
    except (RuntimeError, TypeError, ValueError):
        return False


def _materialize(source: GitInstruction, *, slugmap: SlugMap) -> str:
    content = source.content.strip()
    instruction = Instruction(
        slug=source.slug,
        title=source.title,
        content=content,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        extra_json=source.extra,
    )
    new_key = str(instruction.save(ttl=INSTRUCTION_TTL_SECONDS))
    slugmap.set(source.slug, new_key)
    return new_key


__all__ = [
    "INSTRUCTION_TTL_SECONDS",
    "MIN_REMAINING_INSTRUCTION_TTL_SECONDS",
    "resolve_instruction_key",
]
