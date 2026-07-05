from collections.abc import Iterator, Mapping
from dataclasses import dataclass
import sys
from typing import Any, TextIO

from asc.enqueue.call import create_call_from_manifest_record
from asc.enqueue.plan import LoadedPlan, load_plan_from_manifest_record
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
            _skip_enqueue_row(parsed.line_number, "row must be a JSON object")
            continue

        try:
            record_type = str(raw["record_type"])
        except KeyError:
            _skip_enqueue_row(parsed.line_number, "missing required field: record_type")
            continue

        try:
            call_kind = ENQUEUE_RECORD_TYPES[record_type]
        except KeyError:
            allowed = ", ".join(sorted(ENQUEUE_RECORD_TYPES))
            _skip_enqueue_row(
                parsed.line_number,
                f"record_type must be one of: {allowed}; got {record_type!r}",
            )
            continue

        plan = load_plan_from_manifest_record(raw)

        try:
            call = create_call_from_manifest_record(raw, plan_key=plan.raw_key)
        except Exception as exc:
            _skip_enqueue_row(parsed.line_number, str(exc))
            continue

        yield EnqueueRecord(
            record_type=record_type,
            call_kind=call_kind,
            plan=plan,
            call=call,
            raw_record=raw,
        )

    if not seen:
        print("asc enqueue: no records uploaded", file=sys.stderr)
        return


def _skip_enqueue_row(line_number: int, reason: str) -> None:
    print(f"asc enqueue: skipping row {line_number}: {reason}", file=sys.stderr)


def load_enqueue_records(stream: TextIO) -> list[EnqueueRecord]:
    return list(iter_enqueue_records(stream))


__all__ = [
    "ENQUEUE_RECORD_TYPES",
    "EnqueueRecord",
    "iter_enqueue_records",
    "load_enqueue_records",
]
