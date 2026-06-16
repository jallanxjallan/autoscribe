from __future__ import annotations

import importlib
from typing import Any

from asc.scrivener.connect import LedgerConnection, connect
from asc.scrivener.queries import CONFIRM_EXPORT_SQL, INSERT_CALL_SQL, INSERT_EXPORT_SQL, INSERT_STEP_SQL
from asc.scrivener.schema import ensure_ledger_schema
from asc.scrivener.util import execute_and_commit, json_blob, model_json_blob, timestamp_now


CALL_ACTIONS = {"write_call", "call_started"}
STEP_ACTIONS = {"write_step", "step_written"}
EXPORT_ACTIONS = {"write_export", "call_completed", "export_written"}
CONFIRM_EXPORT_ACTIONS = {"confirm_export", "export_accepted"}

MODEL_MODULES = (
    "asc.models.runtime.call",
    "asc.models.runtime.result",
    "asc.models.runtime.response",
    "asc.models.runtime.failure",
    "asc.models.runtime.job",
    "asc.models.runtime.cursor",
)


def write_job(job: object) -> None:
    with connect() as conn:
        write_job_with_connection(conn=conn, job=job)


def write_job_with_connection(*, conn: LedgerConnection, job: object) -> None:
    ensure_ledger_schema(conn)
    action = _job_action(job)

    if action in CALL_ACTIONS:
        insert_call(conn=conn, job=job)
        return
    if action in STEP_ACTIONS:
        insert_step(conn=conn, job=job)
        return
    if action in EXPORT_ACTIONS:
        insert_export(conn=conn, job=job)
        return
    if action in CONFIRM_EXPORT_ACTIONS:
        confirm_export(conn=conn, job=job)
        return

    raise ValueError(f"unknown scrivener job action: {action}")


def insert_call(*, conn: LedgerConnection, job: object) -> None:
    execute_and_commit(conn, INSERT_CALL_SQL, call_values(job))


def insert_step(*, conn: LedgerConnection, job: object) -> None:
    execute_and_commit(conn, INSERT_STEP_SQL, step_values(job))


def insert_export(*, conn: LedgerConnection, job: object) -> None:
    execute_and_commit(conn, INSERT_EXPORT_SQL, export_values(job))


def confirm_export(*, conn: LedgerConnection, job: object) -> None:
    execute_and_commit(conn, CONFIRM_EXPORT_SQL, confirm_export_values(job))


def call_values(job: object) -> tuple[Any, ...]:
    record = _load_job_input(job)
    return (
        _ledger_identity(job),
        _source_identity(job, record),
        _record_blob(record, fallback=job),
        int(_optional(record, "created_at", default=_optional(job, "created_at", default=timestamp_now()))),
    )


def step_values(job: object) -> tuple[Any, ...]:
    record = _load_job_output(job)
    step_number = int(_required(job, "step_number"))
    if step_number <= 0:
        raise ValueError(f"ledger step_number must be > 0: {step_number}")

    status = _step_status(job, record)
    if status not in {"completed", "failed"}:
        raise ValueError(f"invalid ledger step status: {status}")

    return (
        _ledger_identity(job),
        step_number,
        str(_required(job, "output_key")),
        status,
        _optional(record, "content", default=None),
        _failure_message(record),
        _record_blob(record, fallback=job),
        int(_optional(record, "created_at", default=_optional(job, "created_at", default=timestamp_now()))),
    )


def export_values(job: object) -> tuple[Any, ...]:
    final_step = _final_step(job)
    result_key = _final_result_key(job)
    return (
        _ledger_identity(job),
        final_step,
        result_key,
        _optional(job, "exported_at", default=None),
        _optional(job, "export_message", default=None),
        int(_optional(job, "created_at", default=timestamp_now())),
    )


def confirm_export_values(job: object) -> tuple[Any, ...]:
    return (
        int(_optional(job, "exported_at", default=timestamp_now())),
        _optional(job, "export_message", default=None),
        _ledger_identity(job),
    )


def _job_action(job: object) -> str:
    # ``kind`` is the Redis/model storage kind, e.g. ``ledger-job``.  The
    # ledger operation lives in ``action``.
    return str(_required(job, "action"))


def _ledger_identity(job: object) -> str:
    return str(_required(job, "call_identity"))


def _source_identity(job: object, record: object | None) -> str:
    for obj in (record, job):
        for name in ("source_identity", "record_identity", "source_slug", "slug"):
            value = _optional(obj, name, default=None)
            if value:
                return str(value)
    return str(_required(job, "input_key"))


def _step_status(job: object, record: object | None) -> str:
    explicit = _optional(job, "status", default=None)
    if explicit:
        return str(explicit)
    output_model = str(_optional(job, "output_model", default="")).lower()
    if "failure" in output_model or "fail" in output_model:
        return "failed"
    if _failure_message(record):
        return "failed"
    return "completed"


def _failure_message(record: object | None) -> str | None:
    for name in ("fail_message", "failure_reason", "error", "message"):
        value = _optional(record, name, default=None)
        if value:
            return str(value)
    return None


def _final_step(job: object) -> int:
    explicit = _optional(job, "final_step", default=None)
    if explicit is not None:
        return int(explicit)
    step_number = int(_optional(job, "step_number", default=0) or 0)
    if step_number > 0:
        return step_number
    cursor = _load_cursor(job)
    for name in ("completed_step_count", "current_step", "total_steps"):
        value = _optional(cursor, name, default=None)
        if value:
            return int(value)
    raise ValueError("export job missing final step number")


def _final_result_key(job: object) -> str:
    explicit = _optional(job, "result_key", default=None)
    if explicit:
        return str(explicit)
    for name in ("input_key", "output_key"):
        value = str(_optional(job, name, default="") or "")
        if ":result." in value or ":failure." in value:
            return value
    output_key = _optional(job, "output_key", default=None)
    if output_key:
        return str(output_key)
    raise ValueError("export job missing final result key")


def _load_job_input(job: object) -> object | None:
    return _load_model_record(
        str(_optional(job, "input_model", default="")),
        str(_optional(job, "input_key", default="")),
    )


def _load_job_output(job: object) -> object | None:
    return _load_model_record(
        str(_optional(job, "output_model", default="")),
        str(_optional(job, "output_key", default="")),
    )


def _load_cursor(job: object) -> object | None:
    return _load_model_record("RuntimeCursor", str(_optional(job, "cursor_key", default="")))


def _load_model_record(model_name: str, key: str) -> object | None:
    if not model_name or not key:
        return None
    for module_name in MODEL_MODULES:
        try:
            module = importlib.import_module(module_name)
            cls = getattr(module, model_name)
        except (ImportError, AttributeError):
            continue
        try:
            return cls.load(key)
        except Exception:
            return None
    return None


def _record_blob(record: object | None, *, fallback: object) -> str:
    if record is None:
        return model_json_blob(fallback)
    raw_json = _optional(record, "raw_json", default=None)
    if raw_json is not None:
        return raw_json if isinstance(raw_json, str) else json_blob(raw_json)
    raw_json_json = _optional(record, "raw_json_json", default=None)
    if raw_json_json is not None:
        return str(raw_json_json)
    source_json = _optional(record, "source_json", default=None)
    if source_json is not None:
        return source_json if isinstance(source_json, str) else json_blob(source_json)
    raw_record_json = _optional(record, "raw_record_json", default=None)
    if raw_record_json is not None:
        return str(raw_record_json)
    return model_json_blob(record)


def _optional(obj: object | None, name: str, *, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _required(obj: object, name: str) -> Any:
    value = _optional(obj, name, default=None)
    if value is None:
        raise ValueError(f"scrivener job missing required field: {name}")
    return value


__all__ = [
    "write_job",
    "write_job_with_connection",
    "insert_call",
    "insert_step",
    "insert_export",
    "confirm_export",
    "call_values",
    "step_values",
    "export_values",
    "confirm_export_values",
]
