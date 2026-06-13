"""Redis-backed state helpers for AutoScribe runtime coordination.

Custody queues:

- orchestrator_queue: state:orchestrator:pending
- worker_queue: state:worker:pending
- worker_outcome_queue: state:worker:outcome

Monitoring index:

- orchestrator_index: state:runtime:active

Queues move cursors. The active index observes cursors.
"""

__all__: list[str] = []
