"""Public inbox for orchestrator posts.

External packages should import only this module and call post(key). The key is
the message. No caller should know the orchestrator inbox implementation.
"""

from asc.redis.key import RedisKey
from asc.state.queue import QueuedKey, RedisQueue

from .handler import require_post_key


ORCHESTRATOR_INBOX_KEY = "control:orchestrator:inbox"

orchestrator_inbox = RedisQueue(ORCHESTRATOR_INBOX_KEY)


def _message_key(claimed: QueuedKey | str | None) -> str | None:
    if claimed is None:
        return None
    if isinstance(claimed, QueuedKey):
        return claimed.identity
    return str(claimed).strip()


def post(key: str | RedisKey) -> str:
    raw, _kind = require_post_key(key)
    orchestrator_inbox.insert(raw)
    return raw


def claim() -> str | None:
    return _message_key(orchestrator_inbox.claim())


def block_claim(*, timeout: int = 0) -> str | None:
    return _message_key(orchestrator_inbox.block_claim(timeout=timeout))


def daemon_claim(
    *,
    timeout: int | None = None,
    empty_limit: int | None = None,
) -> str | None:
    return _message_key(
        orchestrator_inbox.daemon_claim(timeout=timeout, empty_limit=empty_limit)
    )


def count() -> int:
    return orchestrator_inbox.count()


def clear() -> int:
    return orchestrator_inbox.clear()


__all__ = [
    "ORCHESTRATOR_INBOX_KEY",
    "block_claim",
    "claim",
    "clear",
    "count",
    "daemon_claim",
    "post",
]
