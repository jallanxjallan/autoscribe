"""Public inbox for worker tasks.

External packages should import only this module and call post(key). The key is
the message. No caller should know the worker inbox implementation.
"""


from asc.redis.key import RedisKey
from asc.state.queue import RedisQueue


WORKER_INBOX_KEY = "control:worker:inbox"

worker_inbox = RedisQueue(WORKER_INBOX_KEY)


def post(key: str | RedisKey) -> str:
    raw = str(key).strip()
    if not raw:
        raise ValueError("worker inbox expected a non-empty task key")
    worker_inbox.insert(raw)
    return raw


def claim() -> str | None:
    return worker_inbox.claim()


def count() -> int:
    return worker_inbox.count()


def clear() -> int:
    return worker_inbox.clear()


__all__ = [
    "WORKER_INBOX_KEY",
    "post",
    "claim",
    "count",
    "clear",
]