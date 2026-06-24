"""Handle scrivener committed notices.

A committed key means Scrivener finished one ordered ledger task. Scrivener
commits are routing signals for the orchestrator:

* write_call      -> enqueue worker execute_step for the first materialized step
* write_step      -> parked until worker-result routing owns that path
* call_completed  -> terminal acknowledgement
* call_failed     -> terminal acknowledgement

Routing is derived from the committed task's data key and the canonical call
index. The write_call task carries the call record key as data_key; the cursor
and first Step are found from that call identity.
"""

from asc.models.process.task import Committed
from asc.redis.key import RedisKey
from asc.scrivener import inbox as scrivener_inbox
from asc.scrivener.maps import CALLS_TABLE
from asc.worker import inbox as worker_inbox

from ..contracts import (
    SCRIVENER_CALL_COMPLETED,
    SCRIVENER_CALL_FAILED,
    SCRIVENER_WRITE_CALL,
    SCRIVENER_WRITE_STEP,
)
from ..errors import OrchestratorContractError
from ..tasks import make_scrivener_call_completed, make_worker_step
from ._runtime import (
    call_index_for_cursor,
    call_key_for_cursor,
    first_step_key,
    required_text,
    slot_for_key,
)


SCRIVENER_PACKAGE = "scrivener"


def handle(key: RedisKey) -> None:
    """Route one committed task notice."""

    committed = Committed.load(str(key))

    package = getattr(committed, "package", "")
    if package and package != SCRIVENER_PACKAGE:
        raise OrchestratorContractError(
            f"unexpected committed package {package!r}: {committed.raw_key}"
        )

    if committed.action == SCRIVENER_WRITE_CALL:
        _dispatch_first_worker_step(committed)
        return

    if committed.action == SCRIVENER_WRITE_STEP:
        # Worker response/failure routing owns normal step progression. A
        # write_step commit is an acknowledgement, not a new route trigger.
        return

    if committed.action in {SCRIVENER_CALL_COMPLETED, SCRIVENER_CALL_FAILED}:
        return

    raise OrchestratorContractError(
        f"unknown scrivener committed action {committed.action!r}: {committed.raw_key}"
    )


def _dispatch_first_worker_step(committed: Committed) -> None:
    data_key = required_text(getattr(committed, "data_key", None), "committed.data_key")
    call_key = RedisKey(data_key)
    if call_key.kind != "call":
        raise OrchestratorContractError(
            f"write_call commit expected call data_key; got {data_key!r}"
        )

    cursor = _cursor_from_call_key(call_key)
    call_index = call_index_for_cursor(cursor)
    step_key = first_step_key(call_index)

    if step_key is None:
        terminal = make_scrivener_call_completed(
            table=CALLS_TABLE,
            data_key=call_key_for_cursor(cursor, call_index),
        )
        terminal.save()
        scrivener_inbox.post(str(terminal.redis_key))
        return

    task = make_worker_step(
        step_key=step_key,
        data_key=call_key_for_cursor(cursor, call_index),
    )
    # Fail loudly if the materialized step is not actually the first slot after
    # the call record. This also catches stale or malformed call indexes early.
    slot_for_key(call_index, step_key)
    task.save()
    worker_inbox.post(str(task.redis_key))


def _cursor_from_call_key(call_key: RedisKey):
    from asc.models.process.cursor import Cursor

    return Cursor.load(f"cursor:{call_key.identity}")


__all__ = ["handle"]
