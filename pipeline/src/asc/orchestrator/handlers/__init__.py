from collections.abc import Callable

from ..contracts import CALL, COMMITTED, FAILURE, RESPONSE

from .call import handle as handle_call
from .committed import handle as handle_committed
from .failure import handle as handle_failure
from .response import handle as handle_response

Handler = Callable[[str], None]

HANDLERS: dict[str, Handler] = {
    CALL: handle_call,
    RESPONSE: handle_response,
    COMMITTED: handle_committed,
    FAILURE: handle_failure,
}

__all__ = ["HANDLERS", "Handler"]
