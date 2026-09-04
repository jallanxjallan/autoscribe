# Git-authoritative Control materialization

- Plans are read directly from the current published Control Git revision at enqueue time and cannot be persisted through the plan model.
- Instructions are lazily materialized with ULID identities and a configurable three-day Redis TTL.
- A cached instruction is reused only when its ULID is newer than the instruction's latest Git commit and at least 24 hours of TTL remain.
- The instruction slugmap points to the preferred materialization; superseded keys are left untouched to expire naturally.
- The plan/instruction synchronization command, plan Redis handler, and publication-version index have been removed.
- Successful execution artifacts and failures now receive configurable seven-day Redis TTLs.
