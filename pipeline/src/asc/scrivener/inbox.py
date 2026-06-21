"""Public inbox for scrivener tasks.

External packages should import only this module and call post(key). The key is
the message. No caller should know the scrivener inbox implementation.
"""


from asc.redis.key import RedisKey
from asc.state.queue import RedisQueue


SCRIVENER_INBOX_KEY = "control:scrivener:inbox"

scrivener_inbox = RedisQueue(SCRIVENER_INBOX_KEY)


def post(key: str | RedisKey) -> str:
    raw = str(key).strip()
    if not raw:
        raise ValueError("scrivener inbox expected a non-empty task key")
    scrivener_inbox.insert(raw)
    return raw


def claim() -> str | None:
    return scrivener_inbox.claim()


def count() -> int:
    return scrivener_inbox.count()


def clear() -> int:
    return scrivener_inbox.clear()


__all__ = [
    "SCRIVENER_INBOX_KEY",
    "post",
    "claim",
    "count",
    "clear",
]