"""Redis-backed state helpers for AutoScribe runtime coordination.

The active queue surface is intentionally small:

- orchestrator_queue: pending call identities awaiting orchestration
- worker_queue: concrete runtime step keys awaiting execution

Slug resolution remains in slugmap. Runtime step/content progression belongs to
Orchestrator, not to state indices.
"""

__all__: list[str] = []
