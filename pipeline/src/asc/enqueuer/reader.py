from __future__ import annotations


# Enqueue accepts more than one external record shape, but there should be only
# one internal enqueue path. The reader is the normalization boundary: inspect
# record_type, hand the raw record to the matching handler, and require that
# handler to return a validated EnqueueManifest containing the loaded Plan and
# ephemeral Call. Most manifests will reference a persistent plan by slug, but a
# handler may also accept an ephemeral plan carried as data in the record, save
# it with a short TTL, and return that transient Plan object instead. This allows
# convenience inputs such as webpage downloads or plain call records to select
# default plans, and batch-specific manifests to carry one-off plans, without
# creating parallel enqueue logic. Once a manifest reaches the service layer,
# every input follows the same response_index, cursor, and queue construction
# path.



from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, TextIO

from asc.enqueuer.call import create_call_from_manifest_record
from asc.enqueuer.plan import LoadedPlan, load_plan_from_manifest_record
from asc.models.process.call import Call
from asc.streams.ndjson import iter_ndjson_records


@dataclass(frozen=True, slots=True)
class EnqueueRecord:
    """One validated run manifest row.

    The stream record itself is a manifest. The reader splits that manifest into
    its persistent plan reference and ephemeral document Call before handing the
    objects to the enqueue service.
    """

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

        record_type = raw["record_type"]

        ALLOWED_RECORD_TYPES = {
            "dispatch-run-manifest",
            "call"
        }

        record_type = raw["record_type"]

        if record_type not in ALLOWED_RECORD_TYPES:
            raise ValueError(
                f"unsupported record_type: {record_type!r}"
            )

        yield EnqueueRecord(
            record_type=record_type,
            plan=load_plan_from_manifest_record(raw),
            call=create_call_from_manifest_record(raw),
            raw_record=raw,
        )
        

    if not seen:
        raise ValueError("no enqueue records found")


def load_enqueue_records(stream: TextIO) -> list[EnqueueRecord]:
    return list(iter_enqueue_records(stream))


__all__ = ["EnqueueRecord", "iter_enqueue_records", "load_enqueue_records"]
