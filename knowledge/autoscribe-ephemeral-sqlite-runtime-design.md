# AutoScribe Runtime State: Ephemeral SQLite Design

## Purpose

Before implementing the sync-daemon set, preserve one architectural decision:

> **Permanent entities live in the physical SQLite database. Ephemeral operational state lives in an in-memory SQLite database owned by the running Rust service.**

This separation is intended to prevent transient execution state from becoming stale durable state, as happened with the lingering `inflight_dispatches` record that continued to make the Dashboard report an active run after the underlying call had completed and exported.

The rule of thumb is simple:

> **If losing a row on reboot would be a problem, it does not belong in the runtime database.**

Conversely:

> **If a row can be reconstructed from authoritative sources at service startup, it should normally be ephemeral.**

---

## 1. Two SQLite Databases

### Persistent database

A normal on-disk SQLite database remains the durable local store.

Typical contents:

- authored plans
- permanent configuration
- stable client identity metadata
- instruction metadata or other permanent references where locally required
- durable mappings that must survive restart
- audit or historical records that are intentionally local
- any other entity whose disappearance after reboot would constitute data loss

Illustrative name:

```text
~/.local/share/autoscribe/service.sqlite
```

This database is **not** the source of truth for what is currently running.

### Runtime database

The Rust service creates a separate SQLite database in memory when it starts.

Typical connection:

```text
:memory:
```

Typical contents:

- active runs
- active calls
- current sync work
- pending downloads
- pending exports
- pending acknowledgements
- transient dispatch/source mappings
- daemon health
- retry timing
- temporary correlation IDs
- current processing state
- values used to generate the Dashboard snapshot

Nothing in this database is expected to survive service shutdown.

---

## 2. Why Use SQLite for Ephemeral State?

The runtime store could be ordinary Rust structures, but SQLite offers several useful properties:

- familiar relational queries
- transactions
- constraints
- explicit schemas
- easy inspection during debugging
- atomic state transitions
- the same general data-access model as the persistent store
- no separate Redis installation or daemon
- no additional client-machine dependency

This gives many of the coordination benefits that might otherwise suggest Redis, without adding another service to arbitrary editor machines.

For the editor client, the preferred stack therefore remains:

```text
Rust service
    +
persistent SQLite
    +
ephemeral SQLite
```

Redis remains an optional server-side technology if later concurrency requirements justify it.

---

## 3. Ownership

The **Rust service owns the runtime database**.

The Obsidian/Electron client does not infer operational state from durable tables.

The sync daemons do not each invent their own competing truth.

Instead, daemon activity is reported into or coordinated through the service-owned runtime state.

Conceptually:

```text
                   ┌─────────────────────┐
                   │ Persistent SQLite   │
                   │ plans, config, etc. │
                   └──────────┬──────────┘
                              │
                              │ durable entities
                              │
┌───────────────┐      ┌──────▼──────────────┐
│ Sync daemons  │─────▶│ Rust service        │
└───────────────┘      │                     │
                       │  runtime SQLite      │
┌───────────────┐      │  (:memory:)         │
│ Pipeline/API  │─────▶│                     │
└───────────────┘      └──────┬──────────────┘
                              │
                              │ snapshot/API
                              ▼
                       ┌───────────────┐
                       │ Client UI     │
                       │ Dashboard     │
                       └───────────────┘
```

---

## 4. Startup Behaviour

At service startup:

1. Open the persistent SQLite database.
2. Create the runtime SQLite database in memory.
3. Create its runtime schema.
4. Query authoritative external/local sources as necessary.
5. Repopulate only state that is genuinely active.
6. Start the sync daemons.
7. Expose the service API and Dashboard snapshot.

The runtime database therefore begins from a known clean state every time.

A reboot becomes a useful state reset rather than a source of ambiguity.

---

## 5. Rebuilding Runtime State

The runtime database must be **reconstructible**.

Possible authoritative inputs include:

- `asc` runtime/run status
- server sync status
- pending server results
- local writeback work that is durably represented elsewhere
- persistent plan/configuration records
- daemon-owned queues that have an authoritative remote equivalent

A runtime row should never be preserved merely because it existed before shutdown.

Instead ask:

> **Is this operation still active according to its authoritative source?**

If yes, recreate it.

If no, do not.

This prevents completed work from remaining “active” forever because a cleanup path failed.

---

## 6. Dashboard Rule

The Dashboard is a **read-only projection of explicit service state**.

It must not derive one operational state by arithmetic on unrelated counters.

For example, avoid logic such as:

```text
processing = active_dispatches - pending_responses
```

Instead, the runtime database/service should expose explicit values:

```text
active_runs
processing_calls
pending_sync
pending_exports
pending_writebacks
daemon_health
```

The UI simply renders them.

If a count is wrong, there is one clear place to debug: the service-owned runtime state.

---

## 7. Durable State vs Runtime State

A useful classification table:

| Entity / State | Persistent DB | Runtime DB |
|---|---:|---:|
| Authored plan | Yes | No |
| Permanent configuration | Yes | No |
| Client identity metadata | Yes | No |
| Active run | No | Yes |
| Active pipeline call | No | Yes |
| Pending sync operation | Usually no | Yes |
| Current retry timer | No | Yes |
| Daemon health | No | Yes |
| Temporary dispatch mapping | No | Yes |
| Dashboard processing counters | No | Yes |
| Historical completed run | Only if deliberately retained as history | No |
| Audit trail required after restart | Yes | No |

The key distinction is **durability requirement**, not which component created the record.

---

## 8. Sync Daemon Implications

When implementing the daemon set, do **not** create permanent SQLite tables merely because a daemon needs somewhere to record current work.

Default daemon pattern:

```text
discover work
    ↓
register transient state in runtime DB
    ↓
perform sync/action
    ↓
update runtime state
    ↓
receive authoritative acknowledgement/result
    ↓
remove transient state
```

If the service crashes halfway through, startup reconstruction determines what remains genuinely outstanding.

The design should therefore prefer **reconciliation** over **recovery from stale local flags**.

---

## 9. Transactions and State Machines

Runtime transitions should still be transactional.

For example:

```text
queued
  ↓
syncing
  ↓
acknowledged
  ↓
removed
```

or:

```text
received
  ↓
processing
  ↓
exported
  ↓
removed
```

The database being ephemeral does not mean the state model should be casual.

SQLite constraints, transactions, and typed Rust APIs should enforce valid transitions.

---

## 10. One Process vs Multiple Processes

A normal SQLite `:memory:` database belongs to a database connection/process context.

Therefore the preferred design is:

> **One Rust service process owns runtime SQLite and coordinates the daemon set.**

The daemons may be logical daemon components/tasks within that service rather than entirely independent OS processes.

If separate connections inside the same process must share an in-memory database, SQLite supports a shared in-memory URI form such as:

```text
file:autoscribe-runtime?mode=memory&cache=shared
```

This requires careful connection lifetime management: the in-memory database exists only while at least one connection remains open.

Do **not** assume that unrelated OS processes can share a normal `:memory:` database.

If the future architecture genuinely requires independent processes, coordination should occur through the owning service API/IPC or another deliberately chosen shared mechanism.

---

## 11. Client-Machine Assumption

For the initial Windows editor client:

> **One AutoScribe installation represents one logical user identity.**

The application does not need to solve general multi-user workstation sharing.

This permits:

- one service instance
- one persistent SQLite store
- one runtime SQLite store
- one client identity
- one credential set
- one daemon set

Shared use of the same Windows account is outside the supported client security model.

A networked content-management office with multiple users, machines, or shared workstations is a different trust and deployment model and should be designed separately.

---

## 12. Security Boundary

The client machine is operationally trusted for the editor's local work, but it is not authoritative for the pipeline.

The important security boundary remains **pipeline ingest**.

A compromised client should not be able to compromise server-side pipeline integrity because ingest must independently enforce:

- authentication
- authorization
- strict payload schemas
- server-owned reference resolution
- replay/idempotency controls
- resource limits
- rejection of arbitrary executable paths/commands
- normalization before execution

Thus ephemeral local runtime state is primarily an operational concern, not a server trust mechanism.

---

## 13. Design Principle for the Daemon Rewrite

When building the sync daemons, resist the temptation to create durable “inflight”, “active”, “processing”, or “pending” tables simply because they are convenient.

First ask:

1. Is this an entity that must survive reboot?
2. Or is it merely a statement about what the system is doing right now?
3. Can the state be reconstructed by reconciliation with an authoritative source?
4. Would persisting it create a second source of truth?

If it describes **what is happening now**, put it in runtime SQLite.

If it describes **what permanently exists or happened**, put it in persistent storage.

---

## 14. Short Form

The intended AutoScribe client-state architecture is:

```text
PERSISTENT SQLITE
    permanent entities
    plans
    config
    durable identity
    intentional history

          +

RUNTIME SQLITE (:memory:)
    active runs
    sync queues
    current processing
    pending acknowledgements
    daemon health
    dashboard state

          +

RUST SERVICE
    owns both stores
    reconciles runtime state at startup
    exposes explicit state to the UI
```

And the governing rule remains:

> **If losing the row on reboot would be a problem, it belongs in persistent storage. Otherwise, prefer runtime state that can be reconstructed from authoritative sources.**
