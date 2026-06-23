from collections.abc import Callable

from asc.redis.key import RedisKey

from .call import handle as handle_call
from .committed import handle as handle_committed
from .failure import handle as handle_failure
from .outcome import handle as handle_outcome
from .response import handle as handle_response

Handler = Callable[[RedisKey], object]

HANDLERS: dict[str, Handler] = {
    "call": handle_call,
    "committed": handle_committed,
    "outcome": handle_outcome,
    "response": handle_response,
    "failure": handle_failure,
}

__all__ = ["HANDLERS", "Handler"]
