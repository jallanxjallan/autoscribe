# AutoScribe Git Transport Architecture
## Recap of architectural decisions — 29 August 2026

This discussion simplified AutoScribe’s configuration and daemon architecture by leaning fully into Git as the durable transport and source of truth.

## 1. Git is the authoritative configuration store

Plans and pipeline instructions should be treated more like code than ordinary content.

They are human-authored and Markdown-friendly, but structurally constrained, versioned, validated, referenced by stable slugs, and capable of changing runtime behavior.

A useful mental model is:

> Pipeline sysmessages are executable configuration: the bastard child of Python and Markdown.

Git therefore becomes the authoritative store for:

- plan definitions;
- instruction definitions;
- historical versions;
- immutable configuration identity;
- reproducibility and audit history.

Redis is not another source of truth. It is a runtime cache/materialization layer.

## 2. Git interaction is wholly manual

The client should not perform background Git synchronization.

All Git publication and retrieval operations are explicitly user-invoked, just like dispatches.

The user may explicitly:

- commit/tag instructions and plans;
- push configuration to the server repo;
- fetch/refresh remote globals;
- dispatch content.

Nothing should silently publish or retrieve configuration merely because files changed.

This makes Git a user-controlled publication boundary.

## 3. No client config daemon

The client-side config watcher is unnecessary and should be removed.

There is no need to:

- watch for dirty instructions or plans;
- compare local hashes with Redis;
- check whether a plan or instruction is already uploaded;
- reconcile local config state in the background;
- maintain a permanent config synchronization daemon.

Obsidian interacts with the local Git repository only.

## 4. No server config daemon

A server-side watcher that processes new config pushes is also unnecessary.

Configuration is resolved lazily when a dispatch reaches `enqueue`.

This removes eager synchronization as a subsystem entirely.

## 5. Enqueue performs lazy configuration materialization

A dispatch identifies:

- the plan slug; and
- the Git commit/config identity that defines the intended configuration universe.

Conceptually:

```text
plan_slug: plan.example
config_commit: <git object id>
```

When `enqueue` receives a dispatch:

1. Check Redis for the exact plan record identified by slug and commit.
2. If present, use it.
3. If absent, open the server Git repo and extract the plan from that commit.
4. Validate the plan.
5. Inspect the plan’s referenced instructions.
6. For each instruction, check Redis for the corresponding slug/commit record.
7. If absent, extract it from the Git repo and create the Redis record.
8. Validate the assembled configuration.
9. Continue enqueue if valid.
10. Fail explicitly if a required plan or instruction cannot be resolved.

Git commit history replaces hash-comparison synchronization logic.

## 6. Redis becomes a true cache

Because the authoritative configuration remains permanently recoverable from Git, Redis configuration records can safely expire.

If a seldom-used instruction ages out of Redis, nothing important is lost.

The next time a dispatch references it, enqueue rehydrates the instruction from the server repo and recreates the runtime record.

This means:

- hot instructions remain cached;
- cold instructions may expire;
- rarely used instructions are resurrected on demand;
- historical dispatches remain reproducible;
- Redis can be treated as disposable runtime state rather than durable configuration storage.

## 7. Globals follow the same Git model

The local repo does not need to contain full copies of every global instruction merely to make them discoverable.

If a user does not see a required global in the UI, they explicitly invoke a refresh/fetch from the server repo.

The UI then rebuilds its available-global view from Git.

The client does not ask the runtime service directly for a global catalog.

Fetch is preferable to an uncontrolled pull because the UI can deliberately update only AutoScribe-owned refs without touching the user’s editorial branch.

## 8. Only two local daemons remain per vault

Each vault now needs only:

- a dispatch daemon;
- a response daemon.

These mirror the asynchronous server-side workers.

### Dispatch daemon

The dispatch daemon handles vault-specific queued dispatch work and makes bounded, fire-and-forget submission attempts.

It does not resolve configuration from Redis or attempt to synchronize plans and instructions.

### Response daemon

The response daemon handles returned results and local reconciliation/write-response work for that vault.

Both daemons are explicitly vault-scoped.

## 9. Daemons are on-demand and disposable

The dispatch and response daemons do not need to run permanently.

The UI can:

1. check whether the required daemon for the current vault is alive;
2. launch it if necessary;
3. leave it running while work is active;
4. allow it to terminate after an idle timeout.

The daemon process itself should own no irreplaceable state.

Restarting a daemon should be routine because durable state belongs elsewhere.

## 10. Final separation of responsibilities

### Git

Owns:

- authored configuration;
- plans and instructions;
- immutable historical versions;
- configuration identity;
- audit trail;
- reproducibility;
- explicit user publication and retrieval.

### Redis

Owns:

- hot runtime materialization;
- cached plan/instruction records;
- temporary execution-facing state.

Redis may forget configuration because Git can recreate it.

### Local operational storage

Owns:

- pending/inflight dispatch bookkeeping;
- response state;
- retries;
- failures;
- reconciliation metadata.

### Daemons

Own only asynchronous work.

They do not own authoritative configuration.

## 11. Architectural summary

The architecture can now be summarized as:

> Git stores durable authored state and exact configuration history. Users explicitly push and fetch that state. Dispatches identify a plan and its Git commit. Enqueue lazily extracts any missing plan or instruction from the server Git repo and materializes it into Redis. Redis is therefore a cache, not a configuration database. Only dispatch and response work requires local daemons, and those daemons are vault-scoped, on-demand, and disposable.

This removes configuration synchronization as a separate subsystem and makes pipeline sysmessages behave much more like versioned source code than ordinary documents.
