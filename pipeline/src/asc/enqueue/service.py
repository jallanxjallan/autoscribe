from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import sys
from typing import Any, TextIO

from asc.enqueue.reader import EnqueueRecord, iter_enqueue_records
from asc.models.runtime.state import CallState
from asc.redis.key import RedisKey
from asc.state.orchestrator_queue import enqueue_call as enqueue_orchestrator_call
from asc.state.slugmap import SLUGMAP_TTL_SECONDS, SlugMap


@dataclass(frozen=True, slots=True)
class EnqueuedCall:
    call: str
    prompt: str
    prompt_key: str
    plan: str
    plan_key: str

    @property
    def call_identity(self) -> str:
        return self.call


@dataclass(frozen=True, slots=True)
class EnqueueReport:
    records: tuple[EnqueuedCall, ...]

    @property
    def record_count(self) -> int:
        return len(self.records)

    @property
    def call_count(self) -> int:
        return len(self.records)

    @property
    def calls(self) -> tuple[str, ...]:
        return tuple(record.call for record in self.records)

    @property
    def call_identities(self) -> tuple[str, ...]:
        return self.calls


def enqueue_from_stream(stream: TextIO) -> EnqueueReport:
    return enqueue_records(iter_enqueue_records(stream))


def enqueue_records(records: Iterable[object]) -> EnqueueReport:
    enqueued: list[EnqueuedCall] = []

    for record_number, record in enumerate(records, start=1):
        try:
            enqueued.append(enqueue_record(record))
        except Exception as exc:
            identifier = _record_identifier(record, fallback=f"record {record_number}")
            print(
                f"[enqueue] {identifier}: skipped invalid dispatch record: {exc}",
                file=sys.stderr,
            )

    return EnqueueReport(records=tuple(enqueued))


def enqueue_record(record: object) -> EnqueuedCall:
    """Resolve dispatch slugs, save call state, and queue the call identity."""

    dispatch = _enqueue_record(record)
    resolver = SlugKeyResolver()

    prompt_key = resolver.resolve(dispatch.prompt_slug, expected_kind="prompt")
    plan_key = resolver.resolve(dispatch.plan_slug, expected_kind="plan")

    call_identity = _identity_from_key(prompt_key)
    plan_identity = _identity_from_key(plan_key)

    CallState(identity=call_identity, plan=plan_identity).save()
    enqueue_call(call_identity)

    return EnqueuedCall(
        call=call_identity,
        prompt=dispatch.prompt_slug,
        prompt_key=prompt_key,
        plan=dispatch.plan_slug,
        plan_key=plan_key,
    )


def enqueue_call(call_identity: str) -> None:
    """Submit a call identity to the orchestrator queue."""

    enqueue_orchestrator_call(call_identity)


def _enqueue_record(record: object) -> EnqueueRecord:
    if isinstance(record, EnqueueRecord):
        return record

    if isinstance(record, Mapping):
        return EnqueueRecord(
            prompt_slug=_required_slug(record, "prompt_slug"),
            plan_slug=_required_slug(record, "plan_slug"),
            raw_record=record,
        )

    model_dump = getattr(record, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return _enqueue_record(dumped)

    raise TypeError("enqueue record must be a mapping or EnqueueRecord")


def _required_slug(record: Mapping[str, Any], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"enqueue record must include {field}")
    return value.strip()


def _record_identifier(record: object, *, fallback: str) -> str:
    try:
        dispatch = _enqueue_record(record)
    except Exception:
        return fallback
    return dispatch.prompt_slug


def _identity_from_key(key: str) -> str:
    """Extract identity from a canonical Redis model key: domain:identity:kind."""

    if not isinstance(key, str) or not key.strip():
        raise ValueError("Redis key must be a non-empty string")

    parts = key.strip().split(":")
    if len(parts) != 3 or not all(parts):
        raise ValueError(f"invalid Redis model key, cannot extract identity: {key}")

    return parts[1]


class SlugKeyResolver:
    """Resolve source slugs into full Redis keys at enqueue time."""

    def __init__(self, slugmap: SlugMap | None = None) -> None:
        self._slugmap = slugmap or SlugMap()

    def resolve(self, value: str, expected_kind: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("slug/key reference must be a non-empty string")

        reference = value.strip()
        if ":" in reference:
            return self._validate_full_key(reference, expected_kind=expected_kind)
        return self._resolve_slug(reference, expected_kind=expected_kind)

    def _resolve_slug(self, slug: str, *, expected_kind: str) -> str:
        return str(self._slugmap.resolve_key(slug, require=True, expected_kind=expected_kind))

    def _validate_full_key(self, key: str, *, expected_kind: str) -> str:
        redis_key = RedisKey(key)
        actual_kind = key.strip().split(":")[-1]
        if actual_kind != expected_kind:
            raise ValueError(
                f"key kind mismatch: expected {expected_kind}, got {actual_kind} ({key})"
            )
        if not redis_key.exists():
            raise KeyError(f"missing key: {key}")
        redis_key.expire(SLUGMAP_TTL_SECONDS)
        return str(redis_key)


__all__ = [
    "SlugKeyResolver",
    "EnqueueReport",
    "EnqueuedCall",
    "enqueue_call",
    "enqueue_from_stream",
    "enqueue_record",
    "enqueue_records",
]