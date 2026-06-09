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
from asc.models.uploaded.record import UploadedRecord
from asc.redis.key import RedisKey
from asc.state.runtime_indices import RuntimeContentIndex, RuntimeStepIndex
from asc.state.step_queue import enqueue_step
from asc.enqueue.reader import EnqueueRecord, iter_enqueue_records

try:  # Current name after the prompt/control slugmap merge.
    from asc.state.slugmap import SLUGMAP_TTL_SECONDS, SlugMap
except ModuleNotFoundError:  # Compatibility with the pre-merge state package.
    from asc.state.control_slugmap import (  # type: ignore[no-redef]
        CONTROL_SLUGMAP_TTL_SECONDS as SLUGMAP_TTL_SECONDS,
        ControlSlugMap as SlugMap,
    )


@dataclass(frozen=True, slots=True)
class EnqueuedCall:
    call: str
    call_key: str
    prompt: str
    prompt_key: str
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
    return enqueue_records(iter_enqueue_records(stream))


def enqueue_records(records: Iterable[object]) -> EnqueueReport:
    enqueued: list[EnqueuedCall] = []

    for record_number, record in enumerate(records, start=1):
        try:
            enqueued.append(enqueue_record(record))
        except Exception as exc:
            identifier = _record_identifier(record, fallback=f"record {record_number}")
            print(f"[enqueue] {identifier}: skipped invalid dispatch record: {exc}", file=sys.stderr)
            continue

    return EnqueueReport(records=tuple(enqueued))


def enqueue_record(record: object) -> EnqueuedCall:
    dispatch = _enqueue_record(record)
    resolver = SlugKeyResolver()

    prompt_key = resolver.resolve(dispatch.prompt_slug, expected_kind="prompt")
    uploaded_prompt = _load_uploaded_prompt(prompt_key)
    raw_prompt_record = _prompt_runtime_record(uploaded_prompt)
    raw_prompt_record.setdefault("prompt_slug", dispatch.prompt_slug)
    raw_prompt_record.setdefault("content", uploaded_prompt.record_content)

    call = generate_identity()

    plan_key = resolver.resolve(dispatch.plan_slug, expected_kind="plan")
    plan_record = PlanRecord.load_from_key(plan_key)
    plan = plan_record.identity
    source_steps = _steps_for_plan_record(plan_record)

    if not source_steps:
        raise ValueError("plan produced no executable steps")

    call_record = RuntimeCallRecord.from_raw_record(
        identity=call,
        raw_record=raw_prompt_record,
        plan=plan,
        plan_key=plan_key,
    )

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
        prompt=dispatch.prompt_slug,
        prompt_key=prompt_key,
        plan=plan,
        plan_key=plan_key,
        first_step_key=first_step_key,
        step_count=len(step_records),
    )


def _enqueue_record(record: object) -> EnqueueRecord:
    if isinstance(record, EnqueueRecord):
        return record

    if isinstance(record, Mapping):
        return EnqueueRecord(
            prompt_slug=_required_slug(record, "prompt_slug"),
            plan_slug=_required_slug(record, "plan_slug"),
            raw_record=record,
        )

    raw_record = getattr(record, "raw_record", None)
    if isinstance(raw_record, Mapping):
        return _enqueue_record(raw_record)

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


def _load_uploaded_prompt(prompt_key: str) -> UploadedRecord:
    loader = getattr(UploadedRecord, "load_from_key", None)
    if callable(loader):
        return loader(prompt_key)

    load = getattr(UploadedRecord, "load", None)
    if callable(load):
        return load(prompt_key)

    redis_key = RedisKey(prompt_key)
    loaded = redis_key.load_model(UploadedRecord)  # type: ignore[attr-defined]
    return loaded


def _prompt_runtime_record(record: UploadedRecord) -> dict[str, Any]:
    raw_record = dict(record.raw_record)
    raw_record.pop("plan_slug", None)

    extras = dict(record.model_extra or {})
    extras.pop("plan_slug", None)
    raw_record.update(extras)

    raw_record.setdefault("record_type", record.record_type)
    raw_record.setdefault("record_identity", record.record_identity)
    raw_record.setdefault("record_content", record.record_content)
    return raw_record


def _steps_for_plan_record(plan_record: PlanRecord) -> Sequence[Any]:
    return plan_record.steps


class SlugKeyResolver:
    """Resolve source slugs into full Redis keys at enqueue time."""

    def __init__(self, slugmap: object | None = None) -> None:
        self._slugmap = slugmap or SlugMap()

    def resolve(self, value: str, expected_kind: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("slug/key reference must be a non-empty string")

        reference = value.strip()

        if ":" in reference:
            return self._validate_full_key(reference, expected_kind=expected_kind)

        resolved = self._resolve_slug(reference, expected_kind=expected_kind)
        return resolved

    def _resolve_slug(self, slug: str, *, expected_kind: str) -> str:
        for method_name in ("resolve_key", "get_key", "lookup_key"):
            method = getattr(self._slugmap, method_name, None)
            if callable(method):
                try:
                    return str(method(slug, require=True, expected_kind=expected_kind))
                except TypeError:
                    return str(method(slug, expected_kind=expected_kind))

        raise TypeError("SlugMap must provide resolve_key(), get_key(), or lookup_key()")

    def _validate_full_key(self, key: str, *, expected_kind: str) -> str:
        redis_key = RedisKey(key)
        actual_kind = redis_key.segments[-1] if redis_key.segments else None
        if actual_kind != expected_kind:
            raise ValueError(
                f"key kind mismatch: expected {expected_kind}, got {actual_kind} ({key})"
            )

        if not redis_key.exists():
            raise KeyError(f"missing key: {key}")

        redis_key.expire(SLUGMAP_TTL_SECONDS)
        return str(redis_key)


# Backwards-compatible name for callers that imported the old resolver directly.
ControlKeyResolver = SlugKeyResolver


__all__ = [
    "ControlKeyResolver",
    "SlugKeyResolver",
    "EnqueueReport",
    "EnqueuedCall",
    "enqueue_from_stream",
    "enqueue_record",
    "enqueue_records",
]
