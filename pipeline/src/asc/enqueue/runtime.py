from asc.redis.key import RedisKey
from asc.redis.primitives.hashes import hset
from asc.redis.primitives.zsets import zadd

ACTIVE_CALLS_KEY = RedisKey("state:active:index")
INITIAL_ACTIVE_SCORE = 0.0


def create_call_index(
    *,
    call_identity: str,
    call_key: str,
    plan_index: dict[str, str],
) -> str:
    """Create the call runtime index by cloning the uploaded plan index.

    The plan index is already materialized by ``asc upload plans`` as
    ``plan:<plan_identity>:index``. Enqueue copies those entries into
    ``call:<call_identity>:index`` and inserts slot ``0`` for the call record.
    """

    if not plan_index:
        raise ValueError("create_call_index() requires a non-empty plan index")

    index_key = RedisKey(kind="call", identity=call_identity, suffix="index")
    mapping = dict(plan_index)
    mapping["0"] = call_key

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
