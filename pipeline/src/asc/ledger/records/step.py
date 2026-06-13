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
    result_timestamp,
)
from asc.models.runtime.result import StepResultRecord
from asc.models.control.step import PlanStepRecord


class StepLedgerError(RuntimeError):
    """Raised when a runtime step cannot be ledgered safely."""


def insert_pending_step_record(
    step: PlanStepRecord,
    *,
    input_content: str,
    input_key: str | None = None,
    output_key: str | None = None,
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
    step: PlanStepRecord,
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
    """Open the configured ledger and finalize one pending step row."""

    with connect() as conn:
        return insert_step_record_with_connection(conn=conn, result=result)


def insert_step_records(results: Sequence[StepResultRecord]) -> list[int]:
    """Open the configured ledger and finalize several pending step rows."""

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
    """Finalize an existing pending/running step row.

    A queued step without a pending ledger row is an invariant violation.
    The orchestrator must fail loudly rather than inventing a completed row.
    """

    call_identity = str(model_value(result, "call_identity"))
    step_number = int(model_value(result, "step_number"))

    existing = fetch_one_dict(
        conn,
        SELECT_STEP_BY_CALL_NUMBER_SQL,
        (call_identity, step_number),
    )

    if existing is None:
        raise StepLedgerError(
            f"no pending step row for call={call_identity} step={step_number}"
        )

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
    step: PlanStepRecord,
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


def completed_step_update_values(result: StepResultRecord) -> tuple[Any, ...]:
    call_identity = str(model_value(result, "call_identity"))
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


def _handler_for_step(step: PlanStepRecord) -> str:
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


def _engine_for_step(step: PlanStepRecord) -> str:
    value = step.definition.get("engine") or step.definition.get("client")
    if isinstance(value, str) and value.strip():
        return value.strip()

    driver_key = step.definition.get("driver_key")
    if isinstance(driver_key, str) and driver_key.strip():
        return driver_key.strip()

    return ""


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
]
