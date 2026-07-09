"""Public inbox for scrivener tasks."""

from asc.redis.key import RedisKey
from asc.state.queue import RedisQueue


SCRIVENER_INBOX_KEY = "control:scrivener:inbox"

scrivener_inbox = RedisQueue(SCRIVENER_INBOX_KEY)


def _message_key(claimed: object) -> str | None:
    if claimed is None:
        return None
    return str(claimed.identity)


def post(key: str | RedisKey) -> str:
    raw = str(key).strip()
    if not raw:
        raise ValueError("scrivener inbox expected a non-empty task key")
    scrivener_inbox.insert(raw)
    return raw


def daemon_claim(*, timeout: int = 0, empty_limit: int | None = None) -> str | None:
    return _message_key(
        scrivener_inbox.daemon_claim(
            timeout=timeout,
            empty_limit=empty_limit,
        )
    )


def block_claim(*, timeout: int = 0) -> str | None:
    return _message_key(scrivener_inbox.block_claim(timeout=timeout))


def claim() -> str | None:
    return _message_key(scrivener_inbox.claim())


def count() -> int:
    return scrivener_inbox.count()


def clear() -> int:
    return scrivener_inbox.clear()


__all__ = [
    "SCRIVENER_INBOX_KEY",
    "post",
    "claim",
    "daemon_claim",
    "block_claim",
    "count",
    "clear",
]
