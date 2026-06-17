from __future__ import annotations

from typing import Final

from asc.models.control.instruction import Instruction
from asc.models.control.plan import Plan
from asc.models.process.call import Call
from asc.redis.model_base import RedisModel

RECORD_TYPE_ALIASES: Final[dict[str, str]] = {
    "instruction": "instruction",
    "instructions": "instruction",
    "call": "call",
    "calls": "call",
    "prompt": "call",
    "prompts": "call",
    "document": "call",
    "documents": "call",
    "plan": "plan",
    "plans": "plan",
}

MODEL_BY_RECORD_TYPE: Final[dict[str, type[RedisModel]]] = {
    "instruction": Instruction,
    "call": Call,
    "plan": Plan,
}


def canonical_record_type(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("record_type must be a non-empty string")

    key = value.strip().lower()
    try:
        return RECORD_TYPE_ALIASES[key]
    except KeyError as exc:
        known = ", ".join(sorted(RECORD_TYPE_ALIASES))
        raise ValueError(f"unknown record_type {value!r}; known: {known}") from exc


def model_for_record_type(record_type: str) -> type[RedisModel]:
    canonical = canonical_record_type(record_type)
    try:
        return MODEL_BY_RECORD_TYPE[canonical]
    except KeyError as exc:
        known = ", ".join(sorted(MODEL_BY_RECORD_TYPE))
        raise ValueError(f"unsupported record_type {record_type!r}; known: {known}") from exc


__all__ = [
    "MODEL_BY_RECORD_TYPE",
    "RECORD_TYPE_ALIASES",
    "canonical_record_type",
    "model_for_record_type",
]
