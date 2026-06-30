from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, TextIO

from asc.enqueuer.call import create_call_from_manifest_record
from asc.enqueuer.plan import LoadedPlan, load_plan_from_manifest_record
from asc.models.process.call import CallRecord
from asc.streams.ndjson import iter_ndjson_records


ENQUEUE_RECORD_TYPES = {
    "content": "call",
    "prompt": "call",
}


@dataclass(frozen=True, slots=True)
class EnqueueRecord:
    """One validated dispatch NDJSON row split into enqueue-ready objects."""

    record_type: str
    call_kind: str
    plan: LoadedPlan
    call: CallRecord
    raw_record: Mapping[str, Any]

    @property
    def source_identity(self) -> str:
        return str(self.call.source_identity)


def iter_enqueue_records(stream: TextIO) -> Iterator[EnqueueRecord]:
    seen = False
    for parsed in iter_ndjson_records(stream):
        seen = True
        raw = parsed.record
        if not isinstance(raw, Mapping):
            raise ValueError(
                f"enqueue stream row {parsed.line_number} must be a JSON object"
            )

        try:
            record_type = str(raw["record_type"])
        except KeyError as exc:
            raise ValueError(
                f"enqueue stream row {parsed.line_number} missing required field: record_type"
            ) from exc

        try:
            call_kind = ENQUEUE_RECORD_TYPES[record_type]
        except KeyError as exc:
            allowed = ", ".join(sorted(ENQUEUE_RECORD_TYPES))
            raise ValueError(
                f"enqueue stream row {parsed.line_number} record_type must be one of: {allowed}"
            ) from exc

        plan = load_plan_from_manifest_record(raw)

        yield EnqueueRecord(
            record_type=record_type,
            call_kind=call_kind,
            plan=plan,
            call=create_call_from_manifest_record(raw, plan_key=plan.raw_key),
            raw_record=raw,
        )

    if not seen:
        raise ValueError("no enqueue records found")


def load_enqueue_records(stream: TextIO) -> list[EnqueueRecord]:
    return list(iter_enqueue_records(stream))


__all__ = [
    "ENQUEUE_RECORD_TYPES",
    "EnqueueRecord",
    "iter_enqueue_records",
    "load_enqueue_records",
]
