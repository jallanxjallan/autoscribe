"""Public inbox for orchestrator posts.

External packages should import only this module and call post(key).  The key is
the message.  No caller should know the orchestrator queue implementation.
"""

from __future__ import annotations

from asc.redis.key import RedisKey
from asc.state import orchestrator_queue

from .contracts import ORCHESTRATOR_POST_KINDS
from .errors import OrchestratorContractError
from .keys import RuntimeKey


def post(key: str | RedisKey) -> str:
    posted = RuntimeKey.parse(key)
    if posted.kind not in ORCHESTRATOR_POST_KINDS:
        expected = ", ".join(sorted(ORCHESTRATOR_POST_KINDS))
        raise OrchestratorContractError(
            f"orchestrator inbox expected one of {expected}; got {posted.kind!r}: {posted.raw}"
        )
    orchestrator_queue.insert(posted.raw)
    return posted.raw


__all__ = ["post"]
