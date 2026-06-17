from __future__ import annotations

from asc.state.response_index import initialize_response_index


def create_response_index(*, identity: str, call_key: str, total_steps: int) -> str:
    """Create the runtime response index and place the call key in slot 0.

    This intentionally depends on one current state API. If that API drifts, it
    should fail loudly instead of probing aliases or silently writing Redis here.
    """

    if total_steps < 1:
        raise ValueError("total_steps must be at least 1")
    return initialize_response_index(
        identity=identity,
        call_key=call_key,
        terminal_step=total_steps,
    )


__all__ = ["create_response_index"]
