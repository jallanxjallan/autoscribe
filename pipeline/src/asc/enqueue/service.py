from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import sys
from typing import Any, TextIO

from asc.core.identity import generate_identity
from asc.ledger.records.call import insert_call_record
from asc.ledger.records.step import insert_pending_step_record
from asc.models.control.plan import PlanRecord, PlanStep
from asc.models.runtime.call import RuntimeCallRecord
from asc.models.runtime.content import RuntimeContentRecord
from asc.models.runtime.step import build_runtime_step_records
from asc.redis.key import RedisKey
from asc.state.control_slugmap import CONTROL_SLUGMAP_TTL_SECONDS, ControlSlugMap
from asc.state.runtime_indices import RuntimeContentIndex, RuntimeStepIndex
from asc.state.step_queue import enqueue_step
from asc.enqueue.reader import iter_atomic_raw_records, require_stream_identity


@dataclass(frozen=True, slots=True)
class EnqueuedCall:
    call_identity: str
    call_key: str
    first_step_key: str
    step_count: int


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
    def step_count(self) -> int:
        return sum(record.step_count for record in self.records)

    @property
    def call_identities(self) -> tuple[str, ...]:
        return tuple(record.call_identity for record in self.records)


def enqueue_from_stream(stream: TextIO) -> EnqueueReport:
    return enqueue_records(iter_atomic_raw_records(stream, allowed_types={"prompt"}))


def enqueue_records(
    records: Iterable[Mapping[str, Any]],
) -> EnqueueReport:
    enqueued: list[EnqueuedCall] = []

    for record_number, record in enumerate(records, start=1):
        try:
            raw_record = require_stream_identity(record, allowed_types={"prompt"})
            enqueued.append(enqueue_record(raw_record))
        except Exception as exc:
            identifier = _record_identifier(record, fallback=f"record {record_number}")
            print(f"[enqueue] {identifier}: skipped invalid prompt: {exc}", file=sys.stderr)
            continue

    return EnqueueReport(records=tuple(enqueued))


def enqueue_record(record: Mapping[str, Any]) -> EnqueuedCall:
    raw_record = require_stream_identity(record, allowed_types={"prompt"})
    call_identity = generate_identity()

    # RuntimeCallRecord owns prompt-row validation/materialization. Enqueue only
    # orchestrates persistence, plan expansion, indices, ledger, and queueing.
    call_record = RuntimeCallRecord.from_raw_record(
        identity=call_identity,
        raw_record=raw_record,
    )

    # Plans are first-class uploaded records. They are addressed by identity
    # directly, not through the old driver/control slugmap path.
    plan_record = PlanRecord.load(call_record.plan_slug)
    source_steps = _steps_for_plan_record(plan_record)

    if not source_steps:
        raise ValueError("plan produced no executable steps")

    resolver = ControlKeyResolver()

    source_content = RuntimeContentRecord.from_source(
        identity=call_identity,
        content=call_record.source_content,
    )
    step_records = build_runtime_step_records(
        identity=call_identity,
        steps=source_steps,
        resolve_control_key=resolver.resolve,
    )

    content_index = RuntimeContentIndex(call_identity)
    step_index = RuntimeStepIndex(call_identity)

    # All runtime writes before this point are disposable. If any operation
    # fails before the ledger rows and queue push, the TTL-governed keys can be
    # abandoned without repair.
    call_key = call_record.save()
    source_content_key = source_content.save()
    content_index.bind_key(1, source_content_key)

    for step_record in step_records:
        step_key = step_record.save()
        step_index.bind_key(step_record.step_number, step_key)

    first_step = step_records[0]
    first_step_key = str(first_step.redis_key)
    output_key = RuntimeContentRecord.key_for_step_result(
        identity=call_identity,
        step_number=first_step.step_number,
    )

    # Durable custody starts here. The executable queue is written last so no
    # worker can claim a step that does not already have a ledger row.
    insert_call_record(call_record)
    insert_pending_step_record(
        first_step,
        input_content=call_record.source_content,
        input_key=source_content_key,
        output_key=output_key,
    )
    enqueue_step(first_step_key)

    return EnqueuedCall(
        call_identity=call_identity,
        call_key=call_key,
        first_step_key=first_step_key,
        step_count=len(step_records),
    )


def _record_identifier(record: object, *, fallback: str) -> str:
    if isinstance(record, Mapping):
        value = record.get("identifier") or record.get("slug")
        if isinstance(value, str) and value.strip():
            return value.strip()

    return fallback


def _steps_for_plan_record(plan_record: PlanRecord) -> Sequence[PlanStep]:
    return plan_record.steps


class ControlKeyResolver:
    """Resolve source slugs into full control keys once, during enqueue."""

    def __init__(self, slugmap: ControlSlugMap | None = None) -> None:
        self._slugmap = slugmap or ControlSlugMap()

    def resolve(self, value: str, expected_kind: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("control reference must be a non-empty string")

        reference = value.strip()

        if ":" in reference:
            return self._validate_full_key(reference, expected_kind=expected_kind)

        resolved = self._slugmap.resolve_key(
            reference,
            require=True,
            expected_kind=expected_kind,
        )
        return resolved

    def _validate_full_key(self, key: str, *, expected_kind: str) -> str:
        redis_key = RedisKey(key)
        actual_kind = redis_key.segments[-1] if redis_key.segments else None
        if actual_kind != expected_kind:
            raise ValueError(
                f"control key kind mismatch: expected {expected_kind}, got {actual_kind} ({key})"
            )

        if not redis_key.exists():
            raise KeyError(f"missing control key: {key}")

        redis_key.expire(CONTROL_SLUGMAP_TTL_SECONDS)
        return str(redis_key)


__all__ = [
    "ControlKeyResolver",
    "EnqueueReport",
    "EnqueuedCall",
    "enqueue_from_stream",
    "enqueue_record",
    "enqueue_records",
]