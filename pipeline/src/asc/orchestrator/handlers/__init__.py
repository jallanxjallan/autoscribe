from collections.abc import Callable

from asc.redis.key import RedisKey

from ..contracts import CALL, OUTCOME

from .call import handle as handle_call
from .outcome import handle as handle_outcome

Handler = Callable[[RedisKey], None]

HANDLERS: dict[str, Handler] = {
    CALL: handle_call,
    OUTCOME: handle_outcome,
}

__all__ = ["HANDLERS", "Handler"]
