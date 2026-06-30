from asc.redis.key import RedisKey
from asc.redis.primitives.hashes import hset
from asc.redis.primitives.zsets import zadd

ACTIVE_CALLS_KEY = RedisKey("state:active:index")
INITIAL_ACTIVE_SCORE = 0.0


def create_call_index(
    *,
    call_identity: str,
    call_key: str,
    step_keys: tuple[str, ...],
) -> str:
    """Create the call runtime index owned by enqueue.

    Slot 0 starts with the call record. Step slots start with the materialized
    process step keys produced by plan upload.
    """

    if not step_keys:
        raise ValueError("create_call_index() requires at least one step key")

    index_key = RedisKey(kind="call", identity=call_identity, suffix="index")
    mapping = {"0": call_key}
    for number, step_key in enumerate(step_keys, start=1):
        mapping[str(number)] = step_key

    hset(index_key, mapping=mapping)
    return str(index_key)


def activate_call(call_key: str) -> None:
    """Put the call record in the active-call zset for orchestration."""

    zadd(ACTIVE_CALLS_KEY, {call_key: INITIAL_ACTIVE_SCORE})


__all__ = [
    "ACTIVE_CALLS_KEY",
    "INITIAL_ACTIVE_SCORE",
    "activate_call",
    "create_call_index",
]
