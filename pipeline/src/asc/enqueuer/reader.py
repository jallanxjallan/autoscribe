# Enqueue accepts external records at the normalization boundary only. The
# current supported input is a dispatch-run manifest row. Future convenience
# inputs, such as pure call records or webpage-download records, should be
# normalized here into this same EnqueueRecord shape rather than adding another
# enqueue path in the service.

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, TextIO

from asc.enqueuer.call import create_call_from_manifest_record
from asc.enqueuer.plan import LoadedPlan, load_plan_from_manifest_record
from asc.models.process.call import Call
from asc.streams.ndjson import iter_ndjson_records


@dataclass(frozen=True, slots=True)
class EnqueueRecord:
    """One validated run manifest row split into enqueue-ready objects."""

    record_type: str
    plan: LoadedPlan
    call: Call
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

        plan = load_plan_from_manifest_record(raw)

        yield EnqueueRecord(
            record_type=record_type,
            plan=plan,
            call=create_call_from_manifest_record(raw, plan_key=plan.raw_key),
            raw_record=raw,
        )

    if not seen:
        raise ValueError("no enqueue records found")


def load_enqueue_records(stream: TextIO) -> list[EnqueueRecord]:
    return list(iter_enqueue_records(stream))


__all__ = [
    "EnqueueRecord",
    "iter_enqueue_records",
    "load_enqueue_records",
]
