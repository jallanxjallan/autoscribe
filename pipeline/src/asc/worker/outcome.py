from typing import Any

from asc.orchestrator import inbox as orchestrator_inbox
from asc.redis.key import RedisKey

INDEX_KEY_FIELDS = (
    "results_index_key",
    "response_index_key",
    "responses_index_key",
    "index_key",
)


def post_worker_outcome(
    *,
    task_key: str,
    cursor_key: str,
    step_number: int,
    output_key: str,
    index_key: str | None = None,
) -> int:
    """Publish a completed worker output to the index and orchestrator inbox.

    The worker owns exactly two side effects after a local script call succeeds:
    write the produced response/failure key into the call's results index slot,
    then hand the worker task key back to the orchestrator inbox. The
    orchestrator remains the only component that decides the next task.
    """

    task_key = _required_text(task_key, "task_key")
    cursor_key = _required_text(cursor_key, "cursor_key")
    output_key = _required_text(output_key, "output_key")
    step_number = int(step_number)
    if step_number < 1:
        raise ValueError(f"worker step_number must be >= 1: {step_number}")

    resolved_index_key = index_key or _find_index_key(task_key=task_key, cursor_key=cursor_key)
    _write_index_slot(
        index_key=resolved_index_key,
        step_number=step_number,
        output_key=output_key,
    )
    return orchestrator_inbox.post(task_key)


def submit_outcome(task_key: str) -> int:
    """Compatibility shim for old callers."""

    raise TypeError(
        "submit_outcome(task_key) is obsolete; use post_worker_outcome with "
        "cursor_key, step_number, and output_key"
    )


def _find_index_key(*, task_key: str, cursor_key: str) -> str:
    task = RedisKey(task_key).hgetall()
    found = _index_key_from_mapping(task)
    if found:
        return found

    cursor = RedisKey(cursor_key).hgetall()
    found = _index_key_from_mapping(cursor)
    if found:
        return found

    identity = _identity_from_mapping(task) or _identity_from_mapping(cursor) or _identity_from_key(cursor_key)
    if identity:
        # DEBT: replace this fallback with the ResultsIndex/RedisKey constructor
        # once model-key construction is centralized.
        return f"results:{identity}"

    raise ValueError(
        "worker task/cursor does not identify a results index; expected one of "
        f"{INDEX_KEY_FIELDS!r} on task or cursor"
    )


def _write_index_slot(*, index_key: str, step_number: int, output_key: str) -> None:
    key = RedisKey(_required_text(index_key, "index_key"))
    key.hset(mapping={str(step_number): output_key})


def _index_key_from_mapping(data: dict[str, Any]) -> str | None:
    for field in INDEX_KEY_FIELDS:
        value = data.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _identity_from_mapping(data: dict[str, Any]) -> str | None:
    value = data.get("identity") or data.get("call_identity")
    if value is None or not str(value).strip():
        return None
    return str(value).strip()


def _identity_from_key(key: str) -> str | None:
    parts = str(key).split(":")
    if len(parts) >= 2 and parts[1].strip():
        return parts[1].strip()
    return None


def _required_text(value: str, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    return text


__all__ = ["post_worker_outcome", "submit_outcome"]
