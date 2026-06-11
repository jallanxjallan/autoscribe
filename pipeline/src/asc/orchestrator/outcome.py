from __future__ import annotations

import logging
from typing import Any

from asc.core.timestamp import timestamp
from asc.ledger.connect import LedgerConnection
from asc.ledger.records.step import insert_step_record_with_connection
from asc.models.runtime.content import RuntimeContentRecord
from asc.models.runtime.result import StepResultRecord
from asc.models.runtime.step import RuntimeStepRecord
from asc.orchestrator.state import (
    call_identity,
    current_step_key,
    current_step_number,
    failure_message,
    input_content_key,
    mark_failed,
    output_content_key,
    save_call_state,
)
from asc.orchestrator.verify import verify_output_artifact

log = logging.getLogger(__name__)


def handle_success(*, conn: LedgerConnection, call_state) -> tuple[StepResultRecord, int]:
    """Persist a successful worker outcome and return its result model + step id.

    The worker owns only execution and response-artifact writing.  The
    orchestrator owns all ledger writes, including finalizing the pending step
    row and later creating the terminal result pointer.
    """

    verify_output_artifact(call_state)
    result = _build_step_result(call_state=call_state, failed=False)
    step_id = insert_step_record_with_connection(
        conn=conn,
        result=result,
        commit=False,
    )
    return result, step_id


def handle_failure(*, conn: LedgerConnection, call_state) -> int:
    """Persist a terminal worker failure after retries are exhausted."""

    result = _build_step_result(call_state=call_state, failed=True)
    step_id = insert_step_record_with_connection(
        conn=conn,
        result=result,
        commit=False,
    )
    mark_failed(call_state)
    save_call_state(call_state)
    log.warning("Recorded terminal worker failure: %s", failure_message(call_state))
    return step_id


def _build_step_result(*, call_state, failed: bool) -> StepResultRecord:
    step_key = current_step_key(call_state)
    prompt_key = input_content_key(call_state)
    response_key = output_content_key(call_state)

    step = RuntimeStepRecord.load(step_key)
    definition = _require_dict(getattr(step, "definition", None), "step.definition")
    args = _optional_dict(definition.get("args"))
    engine = _engine_for_definition(definition)
    handler = _handler_for_definition(definition)

    prompt_content = _content_text(prompt_key)
    response_content = None if failed else _content_text(response_key)
    fail_message = failure_message(call_state) if failed else None

    return StepResultRecord(
        call_identity=call_identity(call_state),
        step_number=current_step_number(call_state),
        raw_json={
            "step_key": step_key,
            "prompt_key": prompt_key,
            "response_key": response_key,
            "engine": engine,
            "args": args,
            "worker_status": getattr(call_state, "worker_status", None),
        },
        content=response_content,
        fail_message=fail_message,
        started_at=getattr(call_state, "started_at", None),
        completed_at=getattr(call_state, "completed_at", None) or timestamp(),
        input_key=prompt_key,
        output_key=response_key,
        handler=handler,
        engine=engine,
        prompt=prompt_content,
        input_content=prompt_content,
    )


def _content_text(key: str) -> str:
    record = RuntimeContentRecord.load(key)
    for field in ("content", "record_content"):
        value = getattr(record, field, None)
        if isinstance(value, str):
            return value
    raise TypeError(f"content artifact has no string content: {key}")


def _engine_for_definition(definition: dict[str, Any]) -> str:
    value = definition.get("engine")
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise TypeError("step.definition.engine must be a non-empty string")


def _handler_for_definition(definition: dict[str, Any]) -> str:
    args = _optional_dict(definition.get("args"))
    for source in (args, definition):
        for key in ("handler", "script", "label"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _optional_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _require_dict(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be an object")
    return value


__all__ = ["handle_failure", "handle_success"]
