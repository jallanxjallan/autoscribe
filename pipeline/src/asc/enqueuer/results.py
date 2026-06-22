from asc.models.process.call import Call
from asc.redis.key import RedisKey
from asc.state.calls import ResultsIndex


def create_results_index(
    *,
    call: Call,
    total_steps: int,
    ttl_seconds: int | None = None,
) -> RedisKey:
    """Create the process results index from the originating Call.

    Slot 0 stores the complete raw Call Redis key. The Call itself remains a
    model instance until the ResultsIndex boundary needs the concrete Redis key.
    Step slots store marker, response, or failure keys.
    """

    call_key = call.redis_key
    if not call_key.identity:
        raise ValueError("call.redis_key.identity must be non-empty")
    if total_steps < 1:
        raise ValueError("total_steps must be positive")

    return ResultsIndex.create(
        call_key=call_key,
        total_steps=total_steps,
        ttl_seconds=ttl_seconds,
    ).redis_key


__all__ = ["create_results_index"]
