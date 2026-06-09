from __future__ import annotations

from collections.abc import Callable

NextStepKeyLookup = Callable[[str, int], str | None]
StepQueueEnqueue = Callable[[str], None]


class OrchestratorContractError(RuntimeError):
    """Raised when a pipeline signal violates orchestration invariants."""


class ScrivenerContractError(OrchestratorContractError):
    """Backward-compatible alias for older imports."""


def default_next_step_key(call_identity: str, next_step_number: int) -> str | None:
    """Return the pre-created runtime key for a step, if it exists.

    The state package owns Redis key/index details. Orchestrator code calls a
    domain-level index accessor or RuntimeStepIndex wrapper, never raw Redis
    hget/hset helpers.
    """

    try:
        from asc.state.step_index import get_step_key
    except ImportError:
        try:
            from asc.state.runtime_indices import RuntimeStepIndex
        except ImportError:
            return None
        index = RuntimeStepIndex(call_identity)
        for method_name in ("get_key", "read_key", "resolve_key"):
            method = getattr(index, method_name, None)
            if callable(method):
                value = method(next_step_number)
                break
        else:
            return None
    else:
        value = get_step_key(call_identity, next_step_number)

    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def default_enqueue_step(step_key: str) -> None:
    """Enqueue a pre-created runtime step key for worker execution."""

    from asc.state.step_queue import enqueue

    enqueue(step_key)
