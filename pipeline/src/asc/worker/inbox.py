"""Public inbox for executable runtime keys."""

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


def _runtime_key(key: str | RedisKey) -> str:
    raw = str(key).strip()
    if not raw:
        raise ValueError("worker inbox expected a non-empty runtime key")

    parsed = RedisKey(raw)
    if parsed.kind != "runtime":
        raise ValueError(
            f"worker inbox accepts runtime keys only, got {parsed.raw_key!r}"
        )
    if parsed.suffix in (None, ""):
        raise ValueError(f"worker runtime key has no ordinal: {parsed.raw_key!r}")
    return parsed.raw_key


def post(key: str | RedisKey) -> str:
    raw = _runtime_key(key)
    worker_inbox.insert(raw)
    return raw


def daemon_claim(*, timeout: int = 0, empty_limit: int | None = None) -> str | None:
    claimed = _message_key(
        worker_inbox.daemon_claim(
            timeout=timeout,
            empty_limit=empty_limit,
        )
    )
    return None if claimed is None else _runtime_key(claimed)


def block_claim(*, timeout: int = 0) -> str | None:
    claimed = _message_key(worker_inbox.block_claim(timeout=timeout))
    return None if claimed is None else _runtime_key(claimed)


def claim() -> str | None:
    claimed = _message_key(worker_inbox.claim())
    return None if claimed is None else _runtime_key(claimed)


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
