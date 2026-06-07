from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import sys
from typing import Any, TextIO

from asc.core.identity import generate_identity
from asc.ledger.call_record import insert_call_record
from asc.ledger.step_record import insert_pending_step_record
from asc.models.control.plan import PlanRecord
from asc.models.runtime.call import RuntimeCallRecord
from asc.models.runtime.content import RuntimeContentRecord
from asc.models.runtime.step import build_runtime_step_records
from asc.redis.key import RedisKey
from asc.state.control_slugmap import CONTROL_SLUGMAP_TTL_SECONDS, ControlSlugMap
from asc.state.runtime_indices import RuntimeContentIndex, RuntimeStepIndex
from asc.state.step_queue import enqueue_step
from asc.enqueue.reader import iter_uploaded_records


@dataclass(frozen=True, slots=True)
class EnqueuedCall:
    call: str
    call_key: str
    plan: str
    plan_key: str
    first_step_key: str
    step_count: int

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
    def step_count(self) -> int:
        return sum(record.step_count for record in self.records)

    @property
    def calls(self) -> tuple[str, ...]:
        return tuple(record.call for record in self.records)

    @property
    def call_identities(self) -> tuple[str, ...]:
        return self.calls


def enqueue_from_stream(stream: TextIO) -> EnqueueReport:
    return enqueue_records(iter_uploaded_records(stream))


def enqueue_records(
    records: Iterable[object],
) -> EnqueueReport:
    enqueued: list[EnqueuedCall] = []

    for record_number, record in enumerate(records, start=1):
        try:
            enqueued.append(enqueue_record(record))
        except Exception as exc:
            identifier = _record_identifier(record, fallback=f"record {record_number}")
            print(f"[enqueue] {identifier}: skipped invalid prompt: {exc}", file=sys.stderr)
            continue

    return EnqueueReport(records=tuple(enqueued))


def enqueue_record(record: object) -> EnqueuedCall:
    raw_record = _raw_mapping_from_uploaded_record(record)
    call = generate_identity()

    plan_slug = _plan_slug_from_record(raw_record)
    plan_key = ControlKeyResolver().resolve(plan_slug, expected_kind="plan")
    plan_record = PlanRecord.load_from_key(plan_key)
    plan = plan_record.identity
    source_steps = _steps_for_plan_record(plan_record)

    if not source_steps:
        raise ValueError("plan produced no executable steps")

    call_record = RuntimeCallRecord.from_raw_record(
        identity=call,
        raw_record=raw_record,
        plan=plan,
        plan_key=plan_key,
    )

    resolver = ControlKeyResolver()

    source_content = RuntimeContentRecord.from_source(
        identity=call,
        content=call_record.source_content,
    )
    step_records = build_runtime_step_records(
        identity=call,
        steps=source_steps,
        resolve_control_key=resolver.resolve,
    )

    content_index = RuntimeContentIndex(call)
    step_index = RuntimeStepIndex(call)

    # Disposable runtime writes. Durable custody begins with ledger rows below.
    call_key = call_record.save()
    source_content_key = source_content.save()
    content_index.bind_key(1, source_content_key)

    for step_record in step_records:
        step_key = step_record.save()
        step_index.bind_key(step_record.step_number, step_key)

    first_step = step_records[0]
    first_step_key = str(first_step.redis_key)
    output_key = RuntimeContentRecord.key_for_step_result(
        identity=call,
        step_number=first_step.step_number,
    )

    # Queue last: a worker should never claim a step before its ledger row exists.
    insert_call_record(call_record)
    insert_pending_step_record(
        first_step,
        input_content=call_record.source_content,
        input_key=source_content_key,
        output_key=output_key,
    )
    enqueue_step(first_step_key)

    return EnqueuedCall(
        call=call,
        call_key=call_key,
        plan=plan,
        plan_key=plan_key,
        first_step_key=first_step_key,
        step_count=len(step_records),
    )


def _plan_slug_from_record(record: Mapping[str, Any]) -> str:
    value = record.get("plan_slug")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("prompt record must include plan_slug")
    return value.strip()


def _record_identifier(record: object, *, fallback: str) -> str:
    raw_record = _raw_mapping_from_uploaded_record(record)
    value = raw_record.get("identifier") or raw_record.get("slug") or raw_record.get("prompt_slug")
    if isinstance(value, str) and value.strip():
        return value.strip()

    return fallback


def _raw_mapping_from_uploaded_record(record: object) -> Mapping[str, Any]:
    if isinstance(record, Mapping):
        return record

    raw_record = getattr(record, "raw_record", None)
    if isinstance(raw_record, Mapping):
        return raw_record

    model_dump = getattr(record, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            raw_record = dumped.get("raw_record")
            if isinstance(raw_record, Mapping):
                return raw_record
            return dumped

    raise TypeError("enqueue record must be a mapping or validated uploaded record")


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
