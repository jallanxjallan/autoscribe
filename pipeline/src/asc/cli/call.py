from asc.core.identity import generate_identity
from asc.enqueuer.reader import EnqueueRecord
from asc.models.process.call import Call


def create_call_from_enqueue_record(record: EnqueueRecord) -> Call:
    """Create the ephemeral call object carried by an enqueue manifest row.

    The enqueue manifest uses the external stream envelope:
    record_type / record_identity / record_content.

    The persisted runtime Call uses the internal process model fields:
    identity / source_identity / content.

    Keep that translation explicit here instead of sending the whole NDJSON row
    through Call.from_ndjson(), because the row now also carries dispatch-only
    fields such as plan_slug.
    """

    call = Call(
        identity=generate_identity(),
        source_identity=record.record_identity,
        content=record.record_content,
    )
    call.save()
    return call


def call_identity(call: Call) -> str:
    return str(call.identity)


def call_key(call: Call) -> str:
    return str(call.redis_key)


__all__ = ["call_identity", "call_key", "create_call_from_enqueue_record"]
