from __future__ import annotations

from typing import Any

from asc.scrivener.util import model_value


def _load_with_model(model: Any, key: str) -> object | None:
    for method_name in ("load", "from_key", "read", "get"):
        method = getattr(model, method_name, None)
        if callable(method):
            return method(key)
    return None


def load_cursor(cursor_key: str) -> object:
    """Load the runtime cursor claimed from the Scrivener queue."""

    candidates: list[Any] = []

    try:
        from asc.models.runtime.cursor import RuntimeCursor  # type: ignore
        candidates.append(RuntimeCursor)
    except ImportError:
        pass

    try:
        from asc.models.runtime.cursor import CursorRecord  # type: ignore
        candidates.append(CursorRecord)
    except ImportError:
        pass

    try:
        from asc.models.runtime.cursor import Cursor  # type: ignore
        candidates.append(Cursor)
    except ImportError:
        pass

    for model in candidates:
        loaded = _load_with_model(model, cursor_key)
        if loaded is not None:
            return loaded

    raise ImportError(
        "could not load runtime cursor; expected asc.models.runtime.cursor "
        "RuntimeCursor/CursorRecord/Cursor with load/from_key/read/get"
    )


def load_job(job_key: str) -> object:
    """Load a Scrivener job record from the runtime job model."""

    candidates: list[Any] = []

    for name in ("ScrivenerJob", "ScrivenerJobRecord", "JobRecord", "Job"):
        try:
            module = __import__("asc.models.runtime.job", fromlist=[name])
            candidates.append(getattr(module, name))
        except (ImportError, AttributeError):
            pass

    for model in candidates:
        loaded = _load_with_model(model, job_key)
        if loaded is not None:
            return loaded

    raise ImportError(
        "could not load scrivener job; expected asc.models.runtime.job "
        "ScrivenerJob/ScrivenerJobRecord/JobRecord/Job with load/from_key/read/get"
    )


def job_key_from_cursor(cursor: object) -> str:
    """Return the explicit Scrivener job reference stored on the cursor.

    No fallback is allowed here.  A cursor in the Scrivener queue without a
    current job is an impossible state: the cursor is immutable, and queue
    custody means the orchestrator already made a concrete handoff decision.
    """

    job_key = model_value(
        cursor,
        "current_job",
        "current_job_key",
        "job_key",
        "job",
        "job_ref",
    )

    if job_key is None or not str(job_key).strip():
        cursor_key = model_value(cursor, "key", "redis_key", "cursor_key", default="<unknown>")
        raise RuntimeError(f"cursor has no current_job: {cursor_key}")

    return str(job_key)

def cursor_key_from_claim(claimed: Any) -> str | None:
    """Normalize queue claim return values to a cursor key string."""

    if claimed is None or claimed is False:
        return None

    if isinstance(claimed, str):
        return claimed

    if isinstance(claimed, bytes):
        return claimed.decode()

    # Redis zpopmin returns [(member, score)]. blpop returns (queue, member).
    if isinstance(claimed, (tuple, list)):
        if len(claimed) == 0:
            return None
        first = claimed[0]
        if isinstance(first, tuple) and first:
            value = first[0]
            return value.decode() if isinstance(value, bytes) else str(value)
        if len(claimed) == 2 and isinstance(claimed[1], (str, bytes)):
            value = claimed[1]
            return value.decode() if isinstance(value, bytes) else str(value)

    value = model_value(claimed, "cursor_key", "cursor", "key", "value", "member")
    return None if value is None else str(value)


__all__ = [
    "cursor_key_from_claim",
    "job_key_from_cursor",
    "load_cursor",
    "load_job",
]
