from __future__ import annotations

from collections.abc import Callable

from ..contracts import COMMITTED, CURSOR, FAILURE, RESPONSE
from ..context import OrchestratorContext
from ..keys import RuntimeKey

from .committed import handle as handle_committed
from .cursor import handle as handle_cursor
from .failure import handle as handle_failure
from .response import handle as handle_response

Handler = Callable[[RuntimeKey, OrchestratorContext], None]

HANDLERS: dict[str, Handler] = {
    CURSOR: handle_cursor,
    RESPONSE: handle_response,
    COMMITTED: handle_committed,
    FAILURE: handle_failure,
}

__all__ = ["HANDLERS", "Handler"]
