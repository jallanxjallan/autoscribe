"""Handle scrivener committed notices.

A committed key means scrivener completed the ordered write and the
orchestrator may continue routing. Deeper continuation policy belongs in the
orchestrator routing layer; this handler is intentionally a minimal acceptance
point while the committed path is being wired back in.
"""

from asc.redis.key import RedisKey


def handle(key: RedisKey) -> bool:
    """Accept a committed notice.

    Returning True gives the daemon/router a simple success value for future
    branching while remaining harmless for current callers that ignore handler
    return values.
    """

    return True


__all__ = ["handle"]
