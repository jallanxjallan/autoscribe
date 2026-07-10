"""Public inbox for worker tasks."""

from asc.redis.key import RedisKey
from asc.state.queue import RedisQueue


WORKER_INBOX_KEY = "control:worker:inbox"

worker_inbox = RedisQueue(WORKER_INBOX_KEY)


def _message_key(claimed: object) -> str | None:
    if claimed is None:
        return None

    key = getattr(claimed, "key", None)
    if key is not None:
        return str(key)

    identity = getattr(claimed, "identity", None)
    if identity is not None:
        return str(identity)

    return str(claimed)


def post(key: str | RedisKey) -> str:
    raw = str(key).strip()
    if not raw:
        raise ValueError("worker inbox expected a non-empty task key")
    worker_inbox.insert(raw)
    return raw


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
