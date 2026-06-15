from __future__ import annotations

from typing import Any


def _call_claim(func: Any, timeout: int | None) -> Any:
    if timeout is None:
        return func()

    for kwargs in (
        {"timeout": timeout},
        {"block_timeout": timeout},
        {"seconds": timeout},
        {},
    ):
        try:
            return func(**kwargs)
        except TypeError:
            continue
    raise TypeError(f"could not call claim function {func!r}")


def _redis_client() -> Any:
    try:
        from asc.state.redis import redis_client  # type: ignore
        return redis_client()
    except Exception:
        pass

    try:
        from asc.state.connect import redis_client  # type: ignore
        return redis_client()
    except Exception:
        pass

    try:
        from asc.state.connect import connect  # type: ignore
        return connect()
    except Exception:
        pass

    import redis

    return redis.Redis(decode_responses=True)


def _module_queue_keys(module: Any, needle: str) -> list[str]:
    keys: list[str] = []
    for name in dir(module):
        upper = name.upper()
        if "KEY" not in upper and "QUEUE" not in upper and "NAME" not in upper:
            continue
        value = getattr(module, name, None)
        if isinstance(value, str) and needle in value and value not in keys:
            keys.append(value)
    return keys


def _claim_from_redis_keys(keys: list[str]) -> Any:
    if not keys:
        return None

    r = _redis_client()
    for key in keys:
        try:
            kind = r.type(key)
            if isinstance(kind, bytes):
                kind = kind.decode()
        except Exception:
            kind = None

        if kind == "zset":
            value = r.zpopmin(key, 1)
            if value:
                return value
        elif kind == "list":
            value = r.lpop(key)
            if value:
                return value
        elif kind == "set":
            value = r.spop(key)
            if value:
                return value

    return None


def _fallback_claim_by_scan(needle: str) -> Any:
    r = _redis_client()
    keys = [str(k) for k in r.scan_iter(f"*{needle}*")]
    # Prefer actual queue-looking names over incidental cursor/job keys.
    keys.sort(key=lambda k: ("queue" not in k, k))
    return _claim_from_redis_keys(keys)


def claim_scrivener_cursor(*, timeout: int | None = None) -> Any:
    from asc.state import scrivener_queue

    for name in ("claim_next", "claim", "dequeue", "pop", "take", "next"):
        func = getattr(scrivener_queue, name, None)
        if callable(func):
            claimed = _call_claim(func, timeout)
            if claimed is not None and claimed is not False:
                return claimed

    claimed = _claim_from_redis_keys(_module_queue_keys(scrivener_queue, "scrivener"))
    if claimed is not None:
        return claimed

    return _fallback_claim_by_scan("scrivener")


def post_cursor_to_orchestrator(cursor_key: str) -> Any:
    from asc.state import orchestrator_queue

    for name in ("enqueue", "post", "push", "add"):
        func = getattr(orchestrator_queue, name, None)
        if callable(func):
            return func(cursor_key)

    keys = _module_queue_keys(orchestrator_queue, "orchestrator")
    if not keys:
        raise AttributeError("asc.state.orchestrator_queue has no enqueue/post function or queue key")

    r = _redis_client()
    key = keys[0]
    kind = r.type(key)
    if isinstance(kind, bytes):
        kind = kind.decode()

    if kind == "list":
        return r.rpush(key, cursor_key)

    # Default current queue shape is score-based.  Use score 0 for ready-now.
    return r.zadd(key, {cursor_key: 0})


__all__ = ["claim_scrivener_cursor", "post_cursor_to_orchestrator"]
