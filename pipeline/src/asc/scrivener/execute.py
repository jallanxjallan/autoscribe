"""Scrivener execution boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass

from asc.ledger.connect import connect
from asc.ledger.schema import ensure_ledger_schema
from asc.ledger.write import table_for, write_task, write_task_with_connection
from asc.models.process.result import Failure
from asc.models.process.task import ScrivenerTask
from asc.redis.key import RedisKey
from asc.redis.primitives import hashes


@dataclass(frozen=True, slots=True)
class _ExecutionReport:
    task_key: str
    artifact_key: str
    failure_key: str | None
    action: str


class ScrivenerExecutor:
    def execute(self, task_key: str) -> _ExecutionReport:
        task_key = _required_text(task_key, "scrivener task key")
        task = ScrivenerTask.load(task_key)

        try:
            with connect() as conn:
                ensure_ledger_schema(conn)
                write_task_with_connection(conn=conn, task=task)
        except Exception as exc:
            failure_key = _save_failure_artifact(
                task=task,
                task_key=task_key,
                exc=exc,
            )
            return _ExecutionReport(
                task_key=task_key,
                artifact_key=failure_key,
                failure_key=failure_key,
                action=task.action,
            )

        artifact_key = _save_committed_artifact(task=task, task_key=task_key)
        return _ExecutionReport(
            task_key=task_key,
            artifact_key=artifact_key,
            failure_key=None,
            action=task.action,
        )


def _save_committed_artifact(*, task: ScrivenerTask, task_key: str) -> str:
    expected_key = _required_task_text(task, "expected_key")
    key = RedisKey(expected_key)
    if key.kind != "committed":
        raise ValueError(f"scrivener expected_key must be committed:<identity>: {expected_key!r}")

    hashes.hset(
        key,
        mapping=_string_mapping(
            {
                "identity": key.identity,
                "task_identity": task.identity,
                "task_key": task_key,
                "package": "scrivener",
                "action": task.action,
                "data_key": task.data_key,
                "table": _task_table(task),
                "result": "committed",
                "status": "success",
            }
        ),
    )
    return key.raw_key


def _save_failure_artifact(
    *,
    task: ScrivenerTask,
    task_key: str,
    exc: Exception,
) -> str:
    failure = _scrivener_failure(
        task=task,
        task_key=task_key,
        exc=exc,
    )
    failure_key = _optional_task_text(task, "failure_key") or RedisKey(
        kind="failure",
        identity=task.identity,
    ).raw_key
    key = RedisKey(failure_key)
    if key.kind != "failure":
        raise ValueError(f"scrivener failure_key must be a failure key: {failure_key!r}")

    saved_key = failure.save(identity=key.identity, suffix=key.suffix)
    if str(saved_key) != key.raw_key:
        raise ValueError(
            "scrivener saved unexpected failure key: "
            f"saved={saved_key!r} expected={key.raw_key!r}"
        )

    return str(saved_key)


def _scrivener_failure(
    *,
    task: ScrivenerTask,
    task_key: str,
    exc: Exception,
) -> Failure:
    error = str(exc)

    raw_json = {
        "task_key": task_key,
        "task_identity": task.identity,
        "data_key": task.data_key,
        "expected_key": _optional_task_text(task, "expected_key") or "",
        "failure_key": _optional_task_text(task, "failure_key") or "",
        "table": _task_table(task),
        "action": task.action,
        "error": error,
        "error_type": type(exc).__name__,
        "boundary": "scrivener.ledger",
    }

    return Failure.model_validate(
        {
            "identity": task.identity,
            "failure_type": "scrivener",
            "content": error,
            "failure_reason": type(exc).__name__,
            "raw_json": raw_json,
            "boundary": "scrivener.ledger",
        }
    )


def _task_table(task: ScrivenerTask) -> str:
    try:
        return table_for(task)
    except Exception:
        value = getattr(task, "table", "")
        return "" if value is None else str(value)


def _string_mapping(raw: dict[str, object]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in raw.items():
        if value is None:
            out[key] = ""
        elif isinstance(value, str):
            out[key] = value
        elif isinstance(value, (dict, list)):
            out[key] = json.dumps(value, sort_keys=True, separators=(",", ":"))
        else:
            out[key] = str(value)
    return out


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_text(value: object, field: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise ValueError(f"{field} must be non-empty")
    return text


def _required_task_text(task: ScrivenerTask, name: str) -> str:
    value = _optional_task_text(task, name)
    if value is None:
        raise ValueError(f"scrivener task {name} must be non-empty: {task.raw_key}")
    return value


def _optional_task_text(task: ScrivenerTask, name: str) -> str | None:
    value = getattr(task, name, None)
    text = "" if value is None else str(value).strip()
    return text or None


__all__ = [
    "ScrivenerExecutor",
    "write_task",
    "write_task_with_connection",
]
