from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, TextIO

from asc.enqueue.call import store_call
from asc.enqueue.plan import LoadedPlan, load_plan
from asc.models.process.call import CallRecord
from asc.streams.ndjson import iter_ndjson_records


@dataclass(frozen=True, slots=True)
class EnqueueRecord:
    """One inline call record plus its plan, resolved at the enqueue boundary."""

    call_slug: str
    plan_slug: str
    call_key: str
    plan: LoadedPlan
    call: CallRecord
    raw_record: Mapping[str, Any]
    directive: str | None = None

    @property
    def source_identity(self) -> str:
        return str(self.call.source_identity)


def iter_enqueue_records(stream: TextIO) -> Iterator[EnqueueRecord]:
    for parsed in iter_ndjson_records(stream):
        raw = parsed.record
        if not isinstance(raw, Mapping):
            raise TypeError(f"row {parsed.line_number} must be a JSON object")
        plan_slug = _required_slug(raw, "plan", parsed.line_number)
        directive = _optional_directive(raw, parsed.line_number)
        call_key, call = store_call(raw)
        yield EnqueueRecord(
            call_slug=str(call.source_identity),
            plan_slug=plan_slug,
            call_key=call_key,
            plan=load_plan(plan_slug),
            call=call,
            raw_record=raw,
            directive=directive,
        )


def _required_slug(raw: Mapping[str, Any], field: str, line_number: int) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"row {line_number} missing required non-empty field: {field}")
    return value.strip()


def _optional_directive(raw: Mapping[str, Any], line_number: int) -> str | None:
    value = raw.get("directive")
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"row {line_number} field directive must be a string or null")
    return value.strip() or None


def load_enqueue_records(stream: TextIO) -> list[EnqueueRecord]:
    return list(iter_enqueue_records(stream))


__all__ = ["EnqueueRecord", "iter_enqueue_records", "load_enqueue_records"]
