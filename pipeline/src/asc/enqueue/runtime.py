from asc.enqueue.plan import LoadedPlan
from asc.models.process.call import CallRecord
from asc.redis.key import RedisKey


ACTIVE_CALLS_KEY = RedisKey(kind="state", identity="active", suffix="index")
INITIAL_ACTIVE_SCORE = 0.0


def create_call_index(*, call: CallRecord, plan: LoadedPlan) -> RedisKey:
    """Clone the uploaded plan index into the runtime call index."""

    if not plan.index:
        raise ValueError("create_call_index() requires a non-empty plan index")

    call_key = call.redis_key
    index_key = RedisKey(kind=call_key.kind, identity=call_key.identity, suffix="index")
    mapping = dict(plan.index)
    mapping["0"] = call_key.raw_key

    index_key.hset(mapping=mapping)
    return index_key


def activate_call(call: CallRecord) -> None:
    """Put the call record in the active-call zset for orchestration."""

    ACTIVE_CALLS_KEY.zadd({call.redis_key.raw_key: INITIAL_ACTIVE_SCORE})


__all__ = ["ACTIVE_CALLS_KEY", "INITIAL_ACTIVE_SCORE", "activate_call", "create_call_index"]
