"""Public inbox for orchestrator posts.

External packages should import only this module and call post(key). The key is
the message. No caller should know the orchestrator inbox implementation.
"""


from asc.redis.key import RedisKey
from asc.state.queue import RedisQueue

from .contracts import ORCHESTRATOR_POST_KINDS
from .errors import OrchestratorContractError
from .keys import RuntimeKey


ORCHESTRATOR_INBOX_KEY = "control:orchestrator:inbox"

orchestrator_inbox = RedisQueue(ORCHESTRATOR_INBOX_KEY)


def post(key: str | RedisKey) -> str:
    posted = RuntimeKey.parse(key)
    if posted.kind not in ORCHESTRATOR_POST_KINDS:
        expected = ", ".join(sorted(ORCHESTRATOR_POST_KINDS))
        raise OrchestratorContractError(
            f"orchestrator inbox expected one of {expected}; got {posted.kind!r}: {posted.raw}"
        )
    orchestrator_inbox.insert(posted.raw)
    return posted.raw


def claim() -> str | None:
    return orchestrator_inbox.claim()


def count() -> int:
    return orchestrator_inbox.count()


def clear() -> int:
    return orchestrator_inbox.clear()


__all__ = [
    "ORCHESTRATOR_INBOX_KEY",
    "post",
    "claim",
    "count",
    "clear",
]