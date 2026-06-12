# service.py
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import sys
from typing import Any, TextIO

from asc.enqueue.plan_steps import ensure_plan_step_records
from asc.enqueue.reader import EnqueueRecord, iter_enqueue_records
from asc.models.runtime.cursor import RuntimeCursor
from asc.state.orchestrator_queue import enqueue as enqueue_orchestrator
from asc.state.slugmap import SlugKeyResolver
from asc.upload.calls import target as call_upload_target


@dataclass(frozen=True, slots=True)
class EnqueuedCall:
    call: str
    call_state_key: str
    call_key: str
    plan_key: str
    step_key: str
    input_key: str
    output_key: str


@dataclass(frozen=True, slots=True)
class EnqueueReport:
    records: tuple[EnqueuedCall, ...]

    @property
    def record_count(self) -> int:
        return len(self.records)

    @property
    def call_count(self) -> int:
        return len(self.records)


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
    dispatch = _enqueue_record(record)
    resolver = SlugKeyResolver()
    call_target = call_upload_target()

    call_key = resolver.resolve(dispatch.prompt_slug, expected_kind=call_target.name)
    plan_key = resolver.resolve(dispatch.plan_slug, expected_kind="plan")

    call_identity = _identity_from_key(call_key, expected_kind=call_target.name)
    ensure_plan_step_records(plan_key)

    call_state = RuntimeCursor(
        identity=call_identity,
        call_key=call_key,
        plan_key=plan_key,
        status="pending",
        current_step=1,
    )
    call_state.save()

    call_state_key = str(call_state.redis_key)
    enqueue_call_state(call_state_key)

    return EnqueuedCall(
        call=call_identity,
        call_state_key=call_state_key,
        call_key=call_key,
        plan_key=plan_key,
        step_key=call_state.step_key,
        input_key=call_state.input_key,
        output_key=call_state.output_key,
    )


def enqueue_call_state(call_state_key: str) -> None:
    if not isinstance(call_state_key, str) or not call_state_key.strip():
        raise ValueError("call_state_key must be a non-empty full Redis key")
    if ":" not in call_state_key:
        raise ValueError(f"call_state_key must be a full Redis key: {call_state_key!r}")
    enqueue_orchestrator(call_state_key.strip())


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
        return _enqueue_record(record).prompt_slug
    except Exception:
        return fallback


def _identity_from_key(key: str, *, expected_kind: str) -> str:
    parts = key.strip().split(":")
    if len(parts) != 3 or not all(parts):
        raise ValueError(f"invalid Redis model key: {key}")
    if parts[2] != expected_kind:
        raise ValueError(
            f"key kind mismatch: expected {expected_kind}, got {parts[2]} ({key})"
        )
    return parts[1]


__all__ = [
    "EnqueueReport",
    "EnqueuedCall",
    "enqueue_call_state",
    "enqueue_from_stream",
    "enqueue_record",
    "enqueue_records",
]