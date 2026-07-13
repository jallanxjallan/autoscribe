from typing import Final

from asc.ingest.common import IngestInputError

RECORD_TYPE_ALIASES: Final[dict[str, str]] = {
    "instruction": "instruction",
    "instructions": "instruction",
    "plan": "plan",
    "plans": "plan",
    "content": "content",
    "contents": "content",
    "call": "content",
    "calls": "content",
    "prompt": "content",
    "prompts": "content",
    "document": "content",
    "documents": "content",
}

TARGET_ALIASES: Final[dict[str, str]] = {
    **RECORD_TYPE_ALIASES,
    "all": "all",
    "records": "all",
}


def canonical_record_type(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IngestInputError("record_type must be a non-empty string")

    key = value.strip().lower()
    try:
        return RECORD_TYPE_ALIASES[key]
    except KeyError as exc:
        known = ", ".join(sorted(RECORD_TYPE_ALIASES))
        raise IngestInputError(f"unknown record_type {value!r}; known: {known}") from exc


def canonical_target(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IngestInputError("target must be a non-empty string")

    key = value.strip().lower()
    try:
        return TARGET_ALIASES[key]
    except KeyError as exc:
        known = ", ".join(sorted(TARGET_ALIASES))
        raise IngestInputError(f"unknown ingest target {value!r}; known: {known}") from exc


__all__ = ["RECORD_TYPE_ALIASES", "TARGET_ALIASES", "canonical_record_type", "canonical_target"]
