from __future__ import annotations

import importlib
from typing import Any

from asc.scrivener.util import json_blob, model_json_blob


MODEL_MODULES = (
    "asc.models.runtime.call",
    "asc.models.runtime.result",
    "asc.models.runtime.response",
    "asc.models.runtime.failure",
    "asc.models.runtime.job",
    "asc.models.runtime.cursor",
)


def job_action(job: object) -> str:
    # ``kind`` is the Redis/model storage kind, e.g. ``ledger-job``.  The
    # ledger operation lives in ``action``.  During the scrivener/ledger naming
    # migration, some job records still carried that operation as ``handler``;
    # accept it here so the writer remains tolerant of queue records produced by
    # either side of the refactor.
    for name in ("action", "handler"):
        value = optional(job, name, default=None)
        if value:
            return str(value)
    raise ValueError("scrivener job missing required field: action/handler")


def ledger_identity(job: object) -> str:
    return str(required(job, "call_identity"))


def source_identity(job: object, record: object | None) -> str:
    for obj in (record, job):
        for name in ("source_identity", "record_identity", "source_slug", "slug"):
            value = optional(obj, name, default=None)
            if value:
                return str(value)
    return str(required(job, "input_key"))


def load_job_input(job: object) -> object | None:
    return load_model_record(
        str(optional(job, "input_model", default="")),
        str(optional(job, "input_key", default="")),
    )


def load_job_output(job: object) -> object | None:
    return load_model_record(
        str(optional(job, "output_model", default="")),
        str(optional(job, "output_key", default="")),
    )


def load_cursor(job: object) -> object | None:
    return load_model_record("RuntimeCursor", str(optional(job, "cursor_key", default="")))


def load_model_record(model_name: str, key: str) -> object | None:
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


def record_blob(record: object | None, *, fallback: object) -> str:
    if record is None:
        return model_json_blob(fallback)
    raw_json = optional(record, "raw_json", default=None)
    if raw_json is not None:
        return raw_json if isinstance(raw_json, str) else json_blob(raw_json)
    raw_json_json = optional(record, "raw_json_json", default=None)
    if raw_json_json is not None:
        return str(raw_json_json)
    source_json = optional(record, "source_json", default=None)
    if source_json is not None:
        return source_json if isinstance(source_json, str) else json_blob(source_json)
    raw_record_json = optional(record, "raw_record_json", default=None)
    if raw_record_json is not None:
        return str(raw_record_json)
    return model_json_blob(record)


def optional(obj: object | None, name: str, *, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def required(obj: object, name: str) -> Any:
    value = optional(obj, name, default=None)
    if value is None:
        raise ValueError(f"scrivener job missing required field: {name}")
    return value


__all__ = [
    "job_action",
    "ledger_identity",
    "source_identity",
    "load_job_input",
    "load_job_output",
    "load_cursor",
    "load_model_record",
    "record_blob",
    "optional",
    "required",
]
