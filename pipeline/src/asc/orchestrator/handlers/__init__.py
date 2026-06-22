from collections.abc import Callable

from ..contracts import CALL, OUTCOME

from .call import handle as handle_call
from .outcome import handle as handle_outcome

Handler = Callable[[str], None]

HANDLERS: dict[str, Handler] = {
    CALL: handle_call,
    OUTCOME: handle_outcome,
}

__all__ = ["HANDLERS", "Handler"]
