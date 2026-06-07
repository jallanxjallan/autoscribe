from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from asc.core.timestamp import timestamp
from asc.ledger.connect import LedgerConnection, connect
from asc.ledger.queries import (
    INSERT_STEP_SQL,
    SELECT_PREVIOUS_COMPLETED_STEP_SQL,
    SELECT_STEP_BY_CALL_NUMBER_SQL,
    SELECT_STEP_SQL,
    SELECT_STEPS_FOR_CALL_SQL,
    STEP_COLUMNS,
    UPDATE_STEP_COMPLETION_SQL,
)
from asc.ledger.util import (
    fetch_all_dicts,
    fetch_one_dict,
    model_json_blob,
    model_value,
)
from asc.models.runtime.call import CallRecord
from asc.models.runtime.result import StepResultRecord
from asc.models.runtime.step import RuntimeStepRecord


class StepLedgerError(RuntimeError):
    """Raised when a runtime step cannot be ledgered safely."""


def insert_pending_step_record(
    step: RuntimeStepRecord,
    *,
    input_content: str,
    input_key: str | None = None,
    output_key: str | None = None
) -> int:
    """Open the configured ledger and persist one pending step custody row."""

    with connect() as conn:
        return insert_pending_step_record_with_connection(
            conn=conn,
            step=step,
            input_content=input_content,
            input_key=input_key,
            output_key=output_key,
        )


def insert_pending_step_record_with_connection(
    *,
    conn: LedgerConnection,
    step: RuntimeStepRecord,
    input_content: str,
    input_key: str | None = None,
    output_key: str | None = None,
    commit: bool = True,
) -> int:
    """Write a pending step row and return its SQL step_id.

    The queue should only receive this step after this row exists.
    """

    existing = fetch_one_dict(
        conn,
        SELECT_STEP_BY_CALL_NUMBER_SQL,
        (step.identity, step.step_number),
    )
    if existing is not None:
        return int(existing["step_id"])

    conn.execute(
        INSERT_STEP_SQL,
        pending_step_values(
            conn=conn,
            step=step,
            input_content=input_content,
            input_key=input_key,
            output_key=output_key,
        ),
    )

    row = fetch_one_dict(
        conn,
        SELECT_STEP_BY_CALL_NUMBER_SQL,
        (step.identity, step.step_number),
    )
    if row is None:
        raise StepLedgerError("inserted pending step row could not be reloaded")

    if commit:
        conn.commit()

    return int(row["step_id"])


def insert_step_record(result: StepResultRecord) -> int:
    """Open the configured ledger and persist one completed/failed step."""

    with connect() as conn:
        return insert_step_record_with_connection(conn=conn, result=result)


def insert_step_records(results: Sequence[StepResultRecord]) -> list[int]:
    """Open the configured ledger and persist several step rows."""

    with connect() as conn:
        step_ids = [
            insert_step_record_with_connection(conn=conn, result=result, commit=False)
            for result in results
        ]
        conn.commit()
        return step_ids


def insert_step_record_with_connection(
    *,
    conn: LedgerConnection,
    result: StepResultRecord,
    commit: bool = True,
) -> int:
    """Write one durable completed/failed step row and return its SQL step_id.

    If enqueue/the worker already inserted a pending row, update that row in
    place. If no pending row exists, insert a completed/failed row using the
    legacy path.
    """

    call_identity = str(model_value(result, "call_identity", "call"))
    step_number = int(model_value(result, "step_number"))

    existing = fetch_one_dict(
        conn,
        SELECT_STEP_BY_CALL_NUMBER_SQL,
        (call_identity, step_number),
    )

    if existing is not None:
        if existing.get("status") not in {"pending", "running"}:
            raise StepLedgerError(
                f"step row already finalized for call={call_identity} step={step_number}"
            )

        conn.execute(UPDATE_STEP_COMPLETION_SQL, completed_step_update_values(result))

        row = fetch_one_dict(
            conn,
            SELECT_STEP_BY_CALL_NUMBER_SQL,
            (call_identity, step_number),
        )
        if row is None:
            raise StepLedgerError("updated step row could not be reloaded")

        if commit:
            conn.commit()

        return int(row["step_id"])

    conn.execute(INSERT_STEP_SQL, step_values(conn=conn, result=result))

    row = fetch_one_dict(
        conn,
        SELECT_STEP_BY_CALL_NUMBER_SQL,
        (call_identity, step_number),
    )
    if row is None:
        raise StepLedgerError("inserted step row could not be reloaded")

    if commit:
        conn.commit()

    return int(row["step_id"])


def read_step_record(step_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        return read_step_record_with_connection(conn=conn, step_id=step_id)


def read_step_record_with_connection(
    *,
    conn: LedgerConnection,
    step_id: int,
) -> dict[str, Any] | None:
    return fetch_one_dict(conn, SELECT_STEP_SQL, (step_id,))


def read_step_records_for_call(call_identity: str) -> list[dict[str, Any]]:
    with connect() as conn:
        return read_step_records_for_call_with_connection(
            conn=conn,
            call_identity=call_identity,
        )


def read_step_records_for_call_with_connection(
    *,
    conn: LedgerConnection,
    call_identity: str,
) -> list[dict[str, Any]]:
    return fetch_all_dicts(conn, SELECT_STEPS_FOR_CALL_SQL, (call_identity,))


def read_previous_completed_step_with_connection(
    *,
    conn: LedgerConnection,
    call_identity: str,
    step_number: int,
) -> dict[str, Any] | None:
    previous_number = step_number - 1
    if previous_number < 1:
        return None

    return fetch_one_dict(
        conn,
        SELECT_PREVIOUS_COMPLETED_STEP_SQL,
        (call_identity, previous_number),
    )


def pending_step_values(
    *,
    conn: LedgerConnection,
    step: RuntimeStepRecord,
    input_content: str,
    input_key: str | None,
    output_key: str | None,
) -> tuple[Any, ...]:
    return (
        step.identity,
        step.step_number,
        _handler_for_step(step),
        _engine_for_step(step),
        "pending",
        input_content,
        None,
        None,
        model_json_blob(step),
        input_key,
        output_key,
        timestamp(),
        None,
        None,
        None,
        None,
        None,
    )

def step_values(*, conn: LedgerConnection, result: StepResultRecord) -> tuple[Any, ...]:
    call_identity = str(model_value(result, "call_identity", "call"))
    step_number = int(model_value(result, "step_number"))

    previous = read_previous_completed_step_with_connection(
        conn=conn,
        call_identity=call_identity,
        step_number=step_number,
    )

    prompt = _prompt_for_step(
        result=result,
        call_identity=call_identity,
        previous=previous,
    )
    response = model_value(result, "content", "response")
    fail_message = model_value(result, "fail_message", "error_message")
    status = "completed" if response is not None else "failed"

    if status == "failed" and fail_message is None:
        raise StepLedgerError("failed step result has no failure detail")

    return (
        call_identity,
        step_number,
        model_value(result, "handler", "script", default=""),
        model_value(result, "engine", "provider", "client", default=""),
        status,
        prompt,
        response,
        fail_message,
        model_json_blob(result),
        model_value(result, "input_key"),
        model_value(result, "output_key"),
        result_timestamp(result),
        model_value(result, "started_at"),
        model_value(result, "completed_at"),
        model_value(result, "prompt_tokens"),
        model_value(result, "completion_tokens"),
        model_value(result, "total_tokens"),
    )

def completed_step_update_values(result: StepResultRecord) -> tuple[Any, ...]:
    call_identity = str(model_value(result, "call_identity", "call"))
    step_number = int(model_value(result, "step_number"))

    response = model_value(result, "content", "response")
    fail_message = model_value(result, "fail_message", "error_message")
    status = "completed" if response is not None else "failed"

    if status == "failed" and fail_message is None:
        raise StepLedgerError("failed step result has no failure detail")

    completed_at = model_value(result, "completed_at") or result_timestamp(result)

    return (
        status,
        response,
        fail_message,
        model_json_blob(result),
        model_value(result, "input_key"),
        model_value(result, "output_key"),
        model_value(result, "started_at"),
        completed_at,
        model_value(result, "prompt_tokens"),
        model_value(result, "completion_tokens"),
        model_value(result, "total_tokens"),
        call_identity,
        step_number,
    )


def _prompt_for_step(
    *,
    result: StepResultRecord,
    call_identity: str,
    previous: dict[str, Any] | None,
) -> str:
    explicit = model_value(
        result,
        "prompt",
        "prompt_content",
        "input_content",
        "input_text",
    )
    if explicit is not None:
        return str(explicit)

    if previous is not None and previous.get("response") is not None:
        return str(previous["response"])

    initial = _initial_prompt_from_call_key(call_identity)
    if initial is not None:
        return initial

    raise StepLedgerError(
        "cannot ledger first step without prompt/input content or a loadable call record"
    )


def _initial_prompt_from_call_key(call_identity: str) -> str | None:
    """Resolve the first prompt from the runtime call key, if available."""

    if not hasattr(CallRecord, "load"):
        return None

    try:
        call = CallRecord.load(call_identity)  # type: ignore[attr-defined]
    except Exception:
        return None

    value = model_value(
        call,
        "source_content",
        "content",
        "prompt",
        "prompt_content",
        "input_content",
        "input_text",
    )
    if value is None:
        return None
    return str(value)


def _handler_for_step(step: RuntimeStepRecord) -> str:
    args = step.definition.get("args")
    if isinstance(args, dict):
        for key in ("handler", "script", "label"):
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    for key in ("handler", "script", "label"):
        value = step.definition.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def _engine_for_step(step: RuntimeStepRecord) -> str:
    value = step.definition.get("engine") or step.definition.get("client")
    if isinstance(value, str) and value.strip():
        return value.strip()

    driver_key = step.definition.get("driver_key")
    if isinstance(driver_key, str) and driver_key.strip():
        return driver_key.strip()

    return ""


def result_timestamp(result: StepResultRecord) -> int:
    if model_value(result, "completed_at") is not None:
        return int(model_value(result, "completed_at"))

    if model_value(result, "started_at") is not None:
        return int(model_value(result, "started_at"))

    if model_value(result, "created_at") is not None:
        return int(model_value(result, "created_at"))

    return timestamp()


__all__ = [
    "STEP_COLUMNS",
    "StepLedgerError",
    "completed_step_update_values",
    "insert_pending_step_record",
    "insert_pending_step_record_with_connection",
    "insert_step_record",
    "insert_step_record_with_connection",
    "insert_step_records",
    "pending_step_values",
    "read_previous_completed_step_with_connection",
    "read_step_record",
    "read_step_record_with_connection",
    "read_step_records_for_call",
    "read_step_records_for_call_with_connection",
    "result_timestamp",
    "step_values",
]
