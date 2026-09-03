# AutoScribe Client IPC and Daemon Architecture — Chat Recap

**Date:** 2 September 2026

## Core architectural correction

IPC has a useful place in a robust client architecture, but only as a **signalling mechanism**, not as a data transport or source of truth.

The governing rule is:

> **IPC says that something happened; durable state says what happened.**

No important dispatch data, plan data, response data, or processing state should exist only inside an IPC message.

---

## Stop trying to infer Obsidian activity

The proposed daemon that attempted to determine whether Obsidian was running, which vaults were open, or what the user was currently doing should be dropped.

That machinery was unnecessarily clever and inherently heuristic.

Obsidian already provides an authoritative indication of user intent: the user explicitly invokes **Dispatch Run**.

Therefore:

1. Dispatch Run records the dispatch intent durably.
2. Dispatch Run sends a small IPC signal telling the relevant daemon to inspect that specific vault.
3. The daemon reads the authoritative filesystem/Git state and determines what work is required.

The service does not need to understand or infer the user's UI activity.

---

## IPC boundary

IPC should carry only a wake-up signal such as:

> inspect this vault

The message may contain enough information to identify the vault or repository, but it should not transport the actual dispatch payload.

The daemon must obtain all substantive information from durable state.

This makes IPC deliberately disposable. A lost IPC message may delay work, but must never lose work.

---

## Lost signals and Dashboard recovery

Because dispatch intent is recorded before signalling the daemon, a lost IPC signal is harmless.

The Dashboard should expose an **Unsent Dispatches** list derived from durable state.

Each unsent dispatch should have a **Resend** or **Retry** action.

That action should merely signal the dispatch daemon to inspect the vault again. It must not create a duplicate dispatch.

Repeated signalling should therefore be harmless and idempotent.

On daemon startup, the daemon should also reconcile existing pending work so that a client crash between writing the dispatch intent and sending IPC cannot strand a run permanently.

---

# Separate dispatch and response daemons

Dispatching and retrieving responses should be handled by **separate daemons**.

They communicate with the same remote system, but they have materially different responsibilities, failure modes, retry rules, and useful lifetimes.

Separating them produces two small, understandable state machines rather than one worker trying to manage both directions of communication.

---

## Dispatch daemon

The dispatch daemon is the **outbound worker**.

Its responsibilities are:

- receive a wake-up signal identifying a vault;
- inspect that vault's durable dispatch state;
- identify unsent or unresolved dispatches;
- assemble the required network request from authoritative local state;
- attempt delivery using a bounded network timeout;
- reconcile the server response;
- record the resulting durable dispatch state;
- retry safely when appropriate.

A useful conceptual state flow is:

`pending -> attempting -> accepted`

with retryable or terminal failure states where necessary.

### Network timeout semantics

A network timeout does **not** necessarily mean the server failed to receive the dispatch.

The server may have accepted the request but the acknowledgement may have been lost.

Therefore a timed-out dispatch should be treated as:

> **delivery state unknown**

rather than immediately as a failed dispatch.

Retries must use the **same stable dispatch/run identity**.

The server-side enqueue operation must consequently be idempotent. A retry should safely resolve to one of:

- already accepted;
- accepted now;
- genuinely rejected/failed.

The daemon should never wait indefinitely for remote confirmation.

---

## Response daemon

The response daemon is the **inbound reconciliation worker**.

Its responsibilities are:

- inspect locally known runs that may have remote responses;
- query the server for completion state;
- tolerate normal "not ready yet" responses;
- retrieve completed responses;
- validate retrieved response data;
- materialize responses into durable client-side inflight state;
- avoid duplicate local responses when the same remote response is retrieved repeatedly.

A useful conceptual state flow is:

`awaiting -> available -> retrieved -> staged`

The response daemon's retry semantics differ from dispatch:

- "nothing ready yet" is normal;
- a network timeout is usually harmless;
- retrieving the same response twice must collapse onto the same response identity;
- response polling must not block dispatch activity.

---

## Why the split matters under unreliable networks

The two-daemon design handles ambiguous network outcomes cleanly.

For example:

1. A dispatch reaches the server.
2. The acknowledgement is lost because of a timeout.
3. The dispatch daemon records an unresolved delivery state.
4. The server processes the run successfully.
5. The response daemon later discovers that a response exists.
6. The dispatch daemon retries using the same dispatch ID.
7. The server reports that the dispatch was already accepted.

Neither daemon needs the other to be continuously alive or healthy.

This is particularly useful where connectivity is intermittent or high-latency.

---

## Daemon lifecycle

Both daemons should be **event-driven but self-reconciling**.

IPC provides immediate wake-up.

Durable queues provide correctness.

### Dispatch daemon

The dispatch daemon can be short-lived:

1. wake;
2. inspect the requested vault;
3. drain relevant pending outbound work;
4. remain alive briefly if useful;
5. exit after a small idle TTL.

### Response daemon

The response daemon may reasonably live somewhat longer because responses arrive asynchronously.

It can:

1. wake after dispatch or when response-related UI is opened;
2. poll with bounded network calls;
3. progressively back off when nothing is ready;
4. reconcile any available responses;
5. terminate after an idle period.

There is no need for either daemon to poll forever.

---

## RAM is optimization, not truth

Neither daemon should keep essential state only in working memory.

RAM may contain transient conveniences such as:

- current backoff intervals;
- open connections;
- recently observed IDs;
- cached metadata;
- temporary work queues.

But restarting either daemon should always be safe.

Durable filesystem/Git/local queue state must be sufficient to reconstruct what needs to happen next.

---

# Responsibility boundaries

The emerging client architecture is:

## Obsidian / UI

Owns:

- explicit user intent;
- Dispatch Run;
- Dashboard presentation;
- manual resend/retry actions;
- user-invoked Write Responses;
- final reviewed writes to master.

It does not need to manage transport state itself.

## Git / filesystem / durable local state

Owns:

- authoritative dispatch intent;
- source state;
- inflight response candidates;
- pending/retryable work;
- reconciliation data required after restart.

## IPC

Owns only:

- wake-up signalling;
- identifying which vault needs inspection.

It is intentionally non-durable.

## Dispatch daemon

Owns:

- outbound reconciliation;
- bounded network dispatch attempts;
- retry/idempotency handling;
- acknowledgement reconciliation.

## Response daemon

Owns:

- remote completion checks;
- response retrieval;
- response deduplication;
- staging retrieved responses into durable inflight state.

## Dashboard

Owns the human-readable recovery surface, including separate views for:

- unsent dispatches;
- uncertain/retryable dispatches;
- awaiting responses;
- retrieved/staged responses;
- failures requiring user attention.

---

# Resulting design principle

The client can now be understood as **two directional workers driven by explicit user intent and durable state**:

`Dispatch Run -> durable outbound intent -> IPC wake-up -> dispatch daemon`

and:

`remote completion -> response daemon -> durable inflight response state -> user Write Responses`

The important consequence is that network failures, daemon crashes, and lost IPC signals become ordinary reconciliation problems rather than data-loss events.

A lost signal merely delays inspection.

A timeout leaves an idempotently retryable uncertainty.

A daemon restart reconstructs work from durable state.

The architecture therefore remains robust without requiring any daemon to infer what Obsidian or the user is doing.
