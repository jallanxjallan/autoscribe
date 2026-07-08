"""Public inbox for worker tasks.

External packages should import only this module and call post(key). The key is
an opaque Redis key string. No caller should know the worker inbox
implementation.
"""

from __future__ import annotations

from asc.redis.key import RedisKey
from asc.state.queue import RedisQueue


WORKER_INBOX_KEY = "control:worker:inbox"

worker_inbox = RedisQueue(WORKER_INBOX_KEY)


def _raw_key(value: object) -> str | None:
    """Return the Redis key carried by RedisQueue claim/post values.

    RedisQueue.claim() returns a QueuedKey-like object whose payload key lives
    at .key. Older code used .identity, which is the queue entry identity /
    wrapper representation, not the task Redis key.
    """
    if value is None:
        return None

    if isinstance(value, RedisKey):
        return value.raw_key

    key = getattr(value, "key", None)
    if key is not None:
        return _raw_key(key)

    raw_key = getattr(value, "raw_key", None)
    if raw_key is not None:
        return str(raw_key).strip()

    return str(value).strip()


def _message_key(claimed: object) -> str | None:
    raw = _raw_key(claimed)
    if raw is None or not raw:
        return None

    task_key = RedisKey(raw)
    if task_key.kind != "task":
        raise ValueError(f"worker inbox claimed non-task key: {raw!r}")

    return task_key.raw_key


def post(key: str | RedisKey) -> str:
    raw = _raw_key(key)
    if raw is None or not raw:
        raise ValueError("worker inbox expected a non-empty task key")

    task_key = RedisKey(raw)
    if task_key.kind != "task":
        raise ValueError(f"worker inbox expected a task key: {raw!r}")

    worker_inbox.insert(task_key.raw_key)
    return task_key.raw_key


def daemon_claim(*, timeout: int = 0, empty_limit: int | None = None) -> str | None:
    return _message_key(
        worker_inbox.daemon_claim(
            timeout=timeout,
            empty_limit=empty_limit,
        )
    )


def block_claim(*, timeout: int = 0) -> str | None:
    return _message_key(worker_inbox.block_claim(timeout=timeout))


def claim() -> str | None:
    return _message_key(worker_inbox.claim())


def count() -> int:
    return worker_inbox.count()


def clear() -> int:
    return worker_inbox.clear()


__all__ = [
    "WORKER_INBOX_KEY",
    "post",
    "claim",
    "daemon_claim",
    "block_claim",
    "count",
    "clear",
]
