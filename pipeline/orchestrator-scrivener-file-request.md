# Files needed: orchestrator + scrivener initiation refactor

Please bundle the following paths from the current AutoScribe source tree. Preserve their directory structure.

## 1. Current orchestrator package

```text
src/asc/orchestrator/
```

I already have the uploaded copy, but include the current repository version so the refactor is made against the exact working tree.

Required especially:

```text
src/asc/orchestrator/active.py
src/asc/orchestrator/daemon.py
src/asc/orchestrator/handle.py
src/asc/orchestrator/inbox.py
src/asc/orchestrator/post_key.py
src/asc/orchestrator/contracts.py
src/asc/orchestrator/errors.py
src/asc/orchestrator/tasks/
src/asc/orchestrator/handlers/
```

## 2. Scrivener package

```text
src/asc/scrivener/
```

Include the entire package: daemon/worker loop, inbox, ledger-write functions, dispatch maps, and package initializers.

The new contract will be:

```text
scrivener inbox item = Redis artifact key only
```

Scrivener will derive the SQLite table from `RedisKey.kind` and insert the artifact hash attributes directly.

## 3. Ledger package and SQLite schema

```text
src/asc/ledger/
```

Include the entire package, especially:

```text
schema creation or migration files
connection/database helpers
insert/upsert helpers
calls table definition
responses table definition
exports table definition
kind-to-table maps
existing views and queries
```

Also include any SQL files stored outside the Python package, for example:

```text
sql/
migrations/
schema/
```

The table columns must be checked against the mandatory model attributes.

## 4. All Redis artifact models

Prefer the complete models package:

```text
src/asc/models/
```

At minimum, include the models defining these durable artifacts:

```text
Call
Response or terminal Result
Export
```

Also include any shared base models and identity types they inherit from.

Likely relevant paths include:

```text
src/asc/models/process/
src/asc/models/content/
src/asc/models/control/
src/asc/models/base.py
src/asc/models/identity.py
```

The check is specifically:

```text
mandatory model attributes == mandatory SQLite row fields
```

ULID identities should remain explicit row primary/foreign-key fields.

## 5. Redis key and primitive helpers

```text
src/asc/redis/
```

Include at least:

```text
src/asc/redis/key.py
src/asc/redis/primitives/hashes.py
src/asc/redis/primitives/keys.py
src/asc/redis/primitives/lists.py
src/asc/redis/primitives/zsets.py
```

Include any Lua scripts or atomic-operation helpers used by these primitives.

This is needed for:

```text
pop active entry
add orchestrator inflight entry
post key to scrivener inbox
replace active score after initiation
```

## 6. Shared state and queue helpers

```text
src/asc/state/
```

Include the entire package, especially:

```text
src/asc/state/queue.py
src/asc/state/calls.py
src/asc/state/daemon.py
```

The existing queue item model may need to be removed or simplified for key-only scrivener messages.

## 7. Enqueuer active-call insertion path

Include the package that creates the call record and inserts it into the active-call zset.

Likely paths may be named one of:

```text
src/asc/enqueue/
src/asc/enqueuer/
src/asc/ingest/
src/asc/commands/enqueue.py
src/asc/cli.py
```

Include whichever files contain:

```text
Call model creation
call:<ULID> Redis persistence
state:active:* ZADD
initial score assignment
```

We need to verify that newly enqueued calls enter the active zset with score `0`.

## 8. Runtime entrypoints and daemon control

Include the files that start and stop the orchestrator and scrivener daemons:

```text
src/asc/run/
src/asc/commands/run.py
src/asc/cli.py
```

Only the actual matching paths are needed. This lets the new initiation daemon be wired into the existing manual daemon-start workflow without restoring automatic startup.

## 9. Existing tests

Include all tests covering these areas:

```text
tests/orchestrator/
tests/scrivener/
tests/ledger/
tests/models/
tests/redis/
tests/state/
tests/enqueue/
```

If tests are organized differently, include every test referencing any of:

```text
active_calls
scrivener
ledger
calls table
responses table
exports table
ScrivenerTask
state:active
failure zset
```

## 10. Project configuration

```text
pyproject.toml
```

Also include any test configuration or dependency lock file needed to run the package tests:

```text
pytest.ini
tox.ini
uv.lock
requirements*.txt
```

Only files that actually exist are needed.

# Preferred bundle

A single archive rooted at the repository root is easiest:

```text
autoscribe-orchestrator-initiation.tar.gz
```

It should contain the paths above without flattening them.

# Scope of this pass

This pass will stop after initial call initiation:

```text
1. Enqueuer leaves call in active zset at score 0.
2. Initiation daemon atomically removes one score-0 call.
3. Initiation daemon posts only the call Redis key to the scrivener inbox.
4. Initiation daemon reinserts the call with its first visibility score.
5. Scrivener derives `calls` from key kind `call`.
6. Scrivener reads the call hash and performs an idempotent row insert/upsert.
7. Calls, responses, and exports schemas are checked against mandatory model attributes.
8. Failures are not written to the ledger.
```

Worker dispatch and result advancement are outside this first implementation boundary unless a shared contract must be adjusted to keep imports and tests valid.
