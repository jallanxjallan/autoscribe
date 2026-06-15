"""Redis-backed runtime custody state.

Invariant:
    one daemon, one inbound queue

Queues:
    state:orchestrator:queue  -> cursor keys for orchestrator
    state:worker:queue        -> cursor keys for workers
    state:scrivener:queue     -> cursor keys for scrivener

Non-queue state:
    state:runtime:active      -> active cursor watchdog zset
    state:slugmap            -> slug -> Redis key resolver

All daemon queues contain cursor keys only. Job/instruction records, when
needed, live outside the queues and are derived from the cursor identity.
"""

__all__: list[str] = []
