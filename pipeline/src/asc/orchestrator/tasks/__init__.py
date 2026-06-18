"""Task factory package for orchestrator routing.

The package is split by destination queue:

* ``common`` contains queue-neutral contract helpers.
* ``worker`` contains worker task construction.
* ``scrivener`` contains scrivener task construction.

This module is only the public import surface used by the orchestrator service.
"""

from .common import (
    RouteDecision,
    ScrivenerTask,
    WorkerTask,
    assert_task_key_for_queue,
    cursor_key_for,
    is_cursor_key,
    key_kind,
    load_task,
    required_text,
    runtime_task_key_for,
    task_key_for,
    task_number_for,
)
from .scrivener import (
    make_call_task,
    make_result_task,
    make_scrivener_call_task,
    make_scrivener_result_task,
    make_scrivener_step_task,
    make_step_task,
)
from .worker import (
    make_task,
    make_worker_task,
    plan_args_for_step,
    plan_step_count,
    step_engine_key,
    step_handler_key,
)

__all__ = [
    "RouteDecision",
    "ScrivenerTask",
    "WorkerTask",
    "assert_task_key_for_queue",
    "cursor_key_for",
    "is_cursor_key",
    "key_kind",
    "load_task",
    "make_call_task",
    "make_result_task",
    "make_scrivener_call_task",
    "make_scrivener_result_task",
    "make_scrivener_step_task",
    "make_step_task",
    "make_task",
    "make_worker_task",
    "plan_args_for_step",
    "plan_step_count",
    "required_text",
    "runtime_task_key_for",
    "step_engine_key",
    "step_handler_key",
    "task_key_for",
    "task_number_for",
]
