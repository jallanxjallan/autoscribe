from asc.redis.key import RedisKey
from asc.state.results import ResultsIndex


def create_results_index(
    *,
    call_key: RedisKey,
    total_steps: int,
    ttl_seconds: int | None = None,
) -> RedisKey:
    """Create the process results index from the originating Call key.

    Slot 0 stores the complete Call Redis key. Step slots store marker,
    response, or failure keys.
    """

    if not call_key.identity:
        raise ValueError("call_key.identity must be non-empty")
    if total_steps < 1:
        raise ValueError("total_steps must be positive")
    
    return ResultsIndex.create(
        call_key=call_key,
        total_steps=total_steps
        ).redis_key
    


__all__ = ["create_results_index"]
