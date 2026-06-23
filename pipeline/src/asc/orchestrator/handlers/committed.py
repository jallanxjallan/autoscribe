"""Handle scrivener committed notices.

A committed key means a package finished one ordered task.  Scrivener commits
are routing signals for the orchestrator:

* write_call      -> enqueue worker execute_step for the first materialized step
* write_step      -> parked until worker-result routing is wired back in
* call_completed  -> terminal acknowledgement
* call_failed     -> terminal acknowledgement

The committed record is expected to contain the copied task fields, especially
package, action, and cursor_key.  The committed key identity may be the task
identity; routing is therefore driven from committed.cursor_key, not from the
committed key identity.
"""

from asc.models.process.cursor import Cursor
from asc.models.process.task import Committed
from asc.redis.key import RedisKey
from asc.scrivener import inbox as scrivener_inbox
from asc.state.calls import CallIndex
from asc.worker import inbox as worker_inbox

from ..contracts import (
    SCRIVENER_CALL_COMPLETED,
    SCRIVENER_CALL_FAILED,
    SCRIVENER_WRITE_CALL,
    SCRIVENER_WRITE_STEP,
)
from ..errors import OrchestratorContractError
from ..tasks import make_scrivener_call_completed, make_worker_step


SCRIVENER_PACKAGE = "scrivener"


def handle(key: RedisKey) -> None:
    """Route one committed task notice."""

    committed = Committed.load(_committed_key(key))

    if committed.package != SCRIVENER_PACKAGE:
        raise OrchestratorContractError(
            f"unexpected committed package {committed.package!r}: {committed.raw_key}"
        )

    if committed.action == SCRIVENER_WRITE_CALL:
        _dispatch_first_worker_step(committed)
        return

    if committed.action == SCRIVENER_WRITE_STEP:
        # Later this should queue the next materialized worker step or terminal
        # scrivener write, once response/failure routing is reattached.
        return

    if committed.action in {SCRIVENER_CALL_COMPLETED, SCRIVENER_CALL_FAILED}:
        return

    raise OrchestratorContractError(
        f"unknown scrivener committed action {committed.action!r}: {committed.raw_key}"
    )


def _committed_key(key: RedisKey) -> str:
    return str(key)


def _dispatch_first_worker_step(committed: Committed) -> None:
    cursor_key = _required_text(
        getattr(committed, "cursor_key", None),
        "committed.cursor_key",
    )
    cursor = Cursor.load(cursor_key)
    call_index = CallIndex.from_identity(cursor.identity)
    step_key = _next_step_key(call_index)

    if step_key is None:
        task = make_scrivener_call_completed(
            cursor=cursor,
            completed_after_step=_last_step_number(call_index),
        )
        task.save()
        scrivener_inbox.post(str(task.redis_key))
        return

    task = make_worker_step(
        cursor_key=cursor_key,
        call_key=str(cursor.call_key),
        step_key=step_key,
        step_number=_slot_for_key(call_index, step_key),
    )
    task.save()
    worker_inbox.post(str(task.redis_key))


def _next_step_key(call_index: CallIndex) -> str | None:
    for slot, key in _ordered_slots(call_index):
        if slot == 0:
            continue
        text = str(key).strip()
        if text and RedisKey(text).kind == "step":
            return text
    return None


def _slot_for_key(call_index: CallIndex, wanted_key: str) -> int:
    for slot, key in _ordered_slots(call_index):
        if str(key).strip() == wanted_key:
            return int(slot)
    raise OrchestratorContractError(
        f"step key {wanted_key!r} is not present in call index {call_index.raw_key}"
    )



def _ordered_slots(call_index: CallIndex) -> list[tuple[int, object]]:
    return sorted(
        ((int(slot), key) for slot, key in call_index.slots().items()),
        key=lambda item: item[0],
    )

def _last_step_number(call_index: CallIndex) -> int:
    slots = [int(slot) for slot in call_index.slots() if int(slot) > 0]
    return max(slots, default=0)


def _required_text(value: object, field_name: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise OrchestratorContractError(f"{field_name} must be non-empty")
    return text


__all__ = ["handle"]
