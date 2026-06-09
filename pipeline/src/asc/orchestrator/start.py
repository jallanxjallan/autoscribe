from __future__ import annotations

from asc.ledger.connect import LedgerConnection
from asc.ledger.records.call import insert_call_record_with_connection
from asc.ledger.records.step import insert_pending_step_record_with_connection
from asc.models.runtime.call import RuntimeCallRecord
from asc.models.runtime.content import RuntimeContentRecord
from asc.models.runtime.step import RuntimeStepRecord
from asc.redis.key import RedisKey

from asc.orchestrator.routing import (
    OrchestratorContractError,
    StepQueueEnqueue,
    default_enqueue_step,
    default_next_step_key,
)


def handle_call_start(
    *,
    conn: LedgerConnection,
    call_key: str,
    enqueue_step: StepQueueEnqueue = default_enqueue_step,
) -> str:
    """Ledger a materialized call and stage its first worker step.

    Enqueue creates the runtime call, source content, step records, and indices,
    then places only the call key on the orchestrator start queue. This function
    is the sole gateway from materialized call to worker execution.
    """

    call = _load_runtime_call(call_key)
    call_identity = str(getattr(call, "identity", getattr(call, "call_identity", "")))
    if not call_identity:
        raise OrchestratorContractError(f"runtime call has no identity: {call_key}")

    first_step_key = default_next_step_key(call_identity, 1)
    if first_step_key is None:
        raise OrchestratorContractError(f"missing first step key for call={call_identity}")

    first_step = _load_runtime_step(first_step_key)
    source_key = _content_key_for_position(call_identity, 1)
    source_content = _load_source_content(source_key)
    output_key = RuntimeContentRecord.key_for_step_result(
        identity=call_identity,
        step_number=first_step.step_number,
    )

    insert_call_record_with_connection(conn=conn, call=call)
    insert_pending_step_record_with_connection(
        conn=conn,
        step=first_step,
        input_content=str(getattr(source_content, "content", getattr(source_content, "record_content", ""))),
        input_key=source_key,
        output_key=output_key,
        commit=False,
    )
    enqueue_step(first_step_key)
    return first_step_key


def _load_runtime_call(call_key: str) -> RuntimeCallRecord:
    for method_name in ("load_from_key", "load"):
        method = getattr(RuntimeCallRecord, method_name, None)
        if callable(method):
            return method(call_key)

    return RedisKey(call_key).load_model(RuntimeCallRecord)  # type: ignore[attr-defined]


def _load_runtime_step(step_key: str) -> RuntimeStepRecord:
    for method_name in ("load_from_key", "load"):
        method = getattr(RuntimeStepRecord, method_name, None)
        if callable(method):
            return method(step_key)

    return RedisKey(step_key).load_model(RuntimeStepRecord)  # type: ignore[attr-defined]


def _load_source_content(content_key: str) -> RuntimeContentRecord:
    for method_name in ("load_from_key", "load"):
        method = getattr(RuntimeContentRecord, method_name, None)
        if callable(method):
            return method(content_key)

    return RedisKey(content_key).load_model(RuntimeContentRecord)  # type: ignore[attr-defined]


def _content_key_for_position(call_identity: str, position: int) -> str:
    try:
        from asc.state.content_index import get_content_key
    except ImportError:
        try:
            from asc.state.runtime_indices import RuntimeContentIndex
        except ImportError as exc:
            raise OrchestratorContractError("no content index accessor available") from exc
        value = RuntimeContentIndex(call_identity).get_key(position)
    else:
        value = get_content_key(call_identity, position)

    if value is None:
        raise OrchestratorContractError(
            f"missing content key for call={call_identity} position={position}"
        )
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


__all__ = ["handle_call_start"]
