# Position Paper: Client-Side IPC as the Control Boundary for AutoScribe

## Executive position

AutoScribe's client should adopt a small, explicit local IPC layer as the sole interface between user-facing code and long-running service processes.

At present, the two most important client operations—dispatching a run and writing responses back into the user's working tree—do not have a proper IPC contract. The current `asc` invocation from the dispatcher is useful as transitional plumbing, but it should not become the permanent application interface. It couples Obsidian-side JavaScript to command-line behavior, process spawning, stdout parsing, executable discovery, environment state, and potentially network latency.

The desired architecture is instead:

**UI code → local IPC → Rust service layer → filesystem/Git/network**

The UI should express intentions. The service layer should perform operations.

A third, system-wide Control daemon should be added alongside the operational dispatch and response services. Its principal responsibility should be to maintain an in-memory, read-optimized representation of published AutoScribe control state—initially the plan catalogue—by periodically polling the remote Control repository.

`Dispatch Run` should obtain its list of available plans from this daemon through local IPC. Opening the dispatch interface should therefore involve no remote request and effectively no perceptible latency.

This also gives AutoScribe a clean place to put future client-side control state without allowing application-specific JavaScript to become a second service implementation.

---

# 1. The architectural problem

The client has progressively acquired a useful separation of responsibilities.

The user owns the content repository's `master` branch.

The Rust service owns automatic processing, ephemeral state, remote communication, and the `autoscribe/inflight` side of the workflow.

Obsidian is increasingly just one possible UI.

This separation is sound, but the interface between UI and service has not yet caught up with it.

Two mission-critical operations illustrate the gap:

1. dispatching content into AutoScribe; and
2. reconciling completed responses back into the working tree.

These operations cross several important boundaries:

- UI process to service process;
- JavaScript to Rust;
- user-owned state to machine-managed state;
- filesystem to Git;
- local state to remote state;
- synchronous user interaction to asynchronous pipeline work.

These are exactly the places where an explicit IPC contract is most valuable.

Without that contract, the current application relies partly on CLI invocation and partly on direct client-side knowledge of implementation details.

That is acceptable during architectural discovery. It is not a good permanent boundary.

---

# 2. `asc` should remain a CLI, not become the application protocol

The `asc` command is valuable.

It provides:

- an administrative interface;
- a debugging interface;
- a scripting interface;
- a way to inspect system state;
- a convenient tool during development;
- a headless interface for operators and automated tooling.

None of those properties make it the ideal runtime interface for Obsidian or a future Electron application.

Calling `asc` from application JavaScript requires the caller to know such things as:

- where the executable is installed;
- how its environment is configured;
- which arguments correspond to which operation;
- which output is intended for humans and which for machines;
- how errors are encoded;
- whether a subprocess has completed;
- whether killing the UI also affects the operation;
- whether the operation requires network access;
- whether stdout or stderr semantics have changed between versions.

It effectively turns the shell into an RPC mechanism.

That is tolerable as scaffolding.

It should not become architecture.

The healthier relationship is:

```text
                         ┌──────────── asc CLI
                         │
UI ── IPC ── service API ┼──────────── Obsidian
                         │
                         └──────────── future Electron UI
```

Both `asc` and graphical interfaces should be clients of the same service capabilities.

The CLI should not sit between the graphical UI and those capabilities.

---

# 3. IPC should be deliberately boring

The client IPC mechanism does not need to be elaborate.

AutoScribe is not building a distributed microservice system inside the user's laptop.

The desirable properties are:

- local only;
- Unix permissions as the principal security boundary;
- extremely low overhead;
- inspectable during development;
- versionable;
- language-neutral;
- tolerant of service restarts;
- easy to consume from JavaScript;
- easy to implement in Rust.

A Unix domain socket carrying newline-delimited JSON remains an excellent fit.

For example:

```json
{"id":"01...", "op":"plans.list", "params":{"scope":"hhp"}}
```

Response:

```json
{
  "id":"01...",
  "ok":true,
  "result":{
    "revision":"8e912...",
    "plans":[
      {
        "slug":"plan.line-edit",
        "label":"Line Edit",
        "description":"..."
      }
    ]
  }
}
```

Nothing stronger is presently required.

The protocol should not expose Rust internals, Git commands, subprocesses, or Redis concepts.

It should expose AutoScribe operations.

---

# 4. Three different kinds of service responsibility

The evolving client naturally separates into three service concerns.

## A. Control service

A small system-wide daemon responsible for obtaining and caching published control information.

Its first job should be maintaining the current plan catalogue.

Its characteristics are:

- one instance per user session or machine;
- not vault-specific;
- mostly read-only;
- network-aware;
- long-lived;
- keeps useful state in memory;
- periodically refreshes from the remote Control repository;
- serves local UI requests immediately.

Possible later responsibilities include:

- instruction catalogue metadata;
- available pipeline capabilities;
- schema/version information;
- service compatibility information;
- user-scoped control options.

It should **not** execute editorial operations.

---

## B. Dispatch service

The operational service responsible for accepting local dispatch requests and getting them safely into the AutoScribe processing system.

Its concerns include:

- identifying source files;
- validating the selected plan;
- recording run identity;
- establishing the inflight source snapshot;
- queueing remote work;
- retrying transient network failures;
- reconciling submission state.

This is vault-sensitive activity.

Whether implemented as one process maintaining short-lived in-memory vault sessions or as vault-scoped workers behind a common socket is an implementation question.

The IPC abstraction should prevent the UI from caring.

---

## C. Response service

The operational service responsible for receiving and preparing machine responses and supporting explicit user-controlled writeback.

Its concerns include:

- retrieving completed responses;
- maintaining response state;
- comparing current master content with dispatched source bytes;
- preparing candidates in `autoscribe/inflight`;
- exposing conflicts or unsafe writes;
- executing only those filesystem/Git operations allocated to the service side of the contract.

The crucial architectural rule remains:

**the daemon does not silently take ownership of the user's master branch.**

IPC should make that rule easier to enforce, not weaken it.

---

# 5. The Control daemon

The proposed Control daemon addresses a particularly clear architectural problem.

The plan list is published remote state, but it is used as interactive UI state.

Those two properties should not be conflated.

A user opening `Dispatch Run` should not need to wait for:

- DNS;
- network routing;
- Git negotiation;
- remote disk activity;
- authentication;
- repository inspection.

The UI needs a list.

Therefore the list should already be local.

The Control daemon can continuously maintain:

```text
Remote Control repository
          │
          │ periodic fetch/poll
          ▼
    Control daemon
          │
          ├── current revision
          ├── plan catalogue
          ├── scope indexes
          └── refresh/error state
          │
          ▼
      local IPC
          │
          ▼
     Dispatch Run
```

From the UI's point of view:

```text
open Dispatch Run
      ↓
plans.list
      ↓
local memory lookup
      ↓
render
```

That should normally take milliseconds.

---

# 6. Memory is the correct primary store for the catalogue

The plan catalogue is neither user content nor authoritative configuration.

It is a derived view of remote authoritative state.

That makes memory an appropriate primary runtime location.

The durable authority remains Git.

The daemon should be able to throw away everything it knows, restart, fetch again, and reconstruct exactly the same catalogue.

This is consistent with the broader AutoScribe design principle:

**Git holds durable configuration; runtime systems hold disposable materializations.**

There is consequently no architectural reason to turn the plan catalogue into another database-backed subsystem.

A tiny optional disk snapshot could eventually improve cold startup under poor connectivity, but that should be regarded as a startup cache, not as another source of truth.

The system should remain correct if that snapshot is deleted.

---

# 7. Polling the Control repository

Polling is appropriate here because the cost of slightly stale catalogue metadata is very low.

There is no need for a complicated push channel.

A sensible process is:

1. fetch the relevant remote Control reference;
2. compare the resulting revision with the daemon's current revision;
3. if unchanged, do nothing;
4. if changed, rebuild the in-memory catalogue;
5. atomically replace the old catalogue;
6. make the new revision visible through IPC.

The daemon should continue serving the last known-good catalogue while refreshing.

It should not clear the catalogue merely because a fetch failed.

This is particularly important for the intended operating environment, where unreliable connectivity is not exceptional.

A failed refresh should yield something like:

```json
{
  "catalogue_revision":"8e912...",
  "fresh":false,
  "last_refresh_error":"network unavailable"
}
```

not:

```json
{
  "plans":[]
}
```

Offline should mean **possibly stale**, not **system unusable**.

---

# 8. Catalogue freshness versus dispatch correctness

The cached catalogue solves an interface problem.

It must not become a correctness dependency.

There is an important difference between:

- displaying a plan to the user; and
- guaranteeing that the plan is valid when a run is enqueued.

The first is a client concern.

The second belongs at the processing boundary.

The UI can therefore select:

```text
plan.line-edit
```

from a cached catalogue.

The dispatch request should carry the plan identity.

At enqueue time the authoritative processing system should still resolve the plan and its referenced instructions from authoritative Git state according to the existing server-side freshness rules.

This gives desirable semantics:

```text
Control daemon:
"What plans can I presently offer the user?"

Server enqueue:
"What exactly does this plan mean at this revision?"
```

Those should remain different questions.

The client catalogue must never quietly become a replicated authoritative configuration database.

---

# 9. IPC for Dispatch Run

The eventual Dispatch Run operation should look conceptually like this:

```text
Obsidian / Electron
       │
       │ plans.list
       ▼
Control service
       │
       └── cached plan metadata

user selects plan
       │
       │ dispatch.create
       ▼
Dispatch service
       │
       ├── validate local repository/source state
       ├── establish run identity
       ├── snapshot required local state
       ├── record pending dispatch
       └── attempt/queue remote enqueue
```

The UI should receive acknowledgment once the local handoff is secure.

For example:

```json
{
  "ok":true,
  "result":{
    "run_id":"run.01...",
    "state":"queued"
  }
}
```

The UI should not remain responsible for the network transaction.

This preserves the existing fire-and-forget objective without confusing it with fire-and-forget process spawning.

The operation has been handed to a durable local service.

That is a meaningful boundary.

---

# 10. IPC for Write Responses

Writeback deserves an equally explicit protocol because it crosses the most sensitive ownership boundary in the client.

The UI needs to ask questions such as:

```text
responses.list
response.inspect
response.write
response.dismiss
```

The service needs to return explicit states such as:

- safe;
- source unchanged;
- local file diverged;
- response missing;
- inflight candidate available;
- already written;
- conflict requires user review.

The UI should never infer these states from filesystem conventions.

Nor should Obsidian JavaScript independently reproduce the comparison and Git logic.

One implementation owns those semantics.

IPC exposes the result.

This becomes especially important once Obsidian is no longer the only client.

The future Electron UI should be able to perform exactly the same write-response workflow without reimplementing AutoScribe's Git rules.

---

# 11. IPC as an architectural anti-corruption layer

The value of IPC here extends beyond communication between processes.

It prevents implementation details leaking upward.

For example, the UI should not know:

```text
refs/heads/autoscribe/inflight
git show
git update-ref
Redis keys
HTTP endpoints
remote bare repository locations
SQLite tables
systemd process names
```

It should know:

```text
plans.list
dispatch.create
dispatch.status
responses.list
response.inspect
response.write
service.status
```

This distinction is important.

The left-hand vocabulary is architecture.

The right-hand vocabulary is implementation.

Correction: from the UI perspective, the **operation vocabulary** is the architecture; the storage/process mechanics are implementation.

A good IPC boundary lets those mechanics change without forcing every UI script to change with them.

---

# 12. One socket or several?

The process topology does not have to dictate the public IPC topology.

The simplest client interface may be one socket such as:

```text
$XDG_RUNTIME_DIR/autoscribe.sock
```

with operations routed internally to:

- control state;
- dispatch state;
- response state.

Alternatively, there could be separate sockets.

The former is preferable unless process isolation creates a strong reason otherwise.

A single application endpoint gives UI code one stable contract:

```text
AutoScribe is available here.
```

The service implementation can then remain free to consist of:

- one supervisor plus workers;
- three independent daemons;
- one process containing three actors;
- a system daemon with per-vault sessions.

This is particularly useful now because the ideal daemon lifecycle is still evolving.

The IPC API can stabilize before the internal process layout does.

---

# 13. The UI should not manage daemon lifecycle directly

A related boundary is lifecycle management.

Obsidian macros should not need to ask:

```text
is control-daemon running?
should I start dispatch-daemon?
where is the PID?
has the response daemon expired?
```

Ideally the service endpoint is simply available.

Systemd user services are well suited to this.

Socket activation would be even cleaner if it proves worthwhile.

Then:

```text
UI connects
    ↓
service exists or is activated
    ↓
operation occurs
```

The choice of a short-lived or long-lived worker remains below the interface.

This eliminates another category of Electron- or Obsidian-specific plumbing.

---

# 14. A useful initial IPC surface

The first API need not be large.

A deliberately small first version could contain:

```text
system.ping
system.status

plans.list
plans.status
plans.refresh

dispatch.create
dispatch.status

responses.list
response.inspect
response.write
```

That is sufficient to remove the most consequential shell boundaries.

It also allows the existing CLI to become a convenient IPC client.

For example:

```text
asc plans list
```

could simply call:

```text
plans.list
```

over the socket.

Likewise:

```text
asc dispatch ...
```

could use the same service operation as Obsidian.

This would make `asc` more useful, not less.

It becomes a human-accessible frontend to the service rather than a parallel implementation.

---

# 15. Versioning

The protocol should be versioned from the start, even if only minimally.

For example:

```json
{
  "protocol":1,
  "id":"...",
  "op":"plans.list",
  "params":{}
}
```

The server can advertise:

```json
{
  "service_version":"0.8.0",
  "protocol_versions":[1]
}
```

This matters because the client UI and Rust service may be updated independently.

A future Electron application intended for less technical users especially needs failures such as:

```text
AutoScribe client is newer than the local service.
Please update the service.
```

rather than malformed JSON or missing-command errors.

---

# 16. Failure semantics

IPC should make failure states explicit.

Every operation should resolve into one of three broad outcomes:

### Operation accepted

The requested local responsibility has been successfully assumed.

Example:

```text
dispatch queued locally
```

### Operation rejected

The local system has enough information to say that the request is invalid.

Example:

```text
source repository is not valid
```

### Operation unavailable

The service cannot presently perform the operation.

Example:

```text
no Control catalogue has ever been fetched and network is unavailable
```

These distinctions are much more useful to a UI than shell exit status plus stderr.

They also allow user-facing messages to remain stable while implementation details change.

---

# 17. What the Control daemon should not become

The new daemon creates a tempting place to accumulate functionality.

That should be resisted.

It should not become:

- another pipeline;
- a client-side plan materializer;
- a Redis replacement;
- a general Git watcher;
- an Obsidian watcher;
- a file indexing daemon;
- a background instruction editor;
- a second authoritative config store.

Its scope should remain:

**maintain cheap local views of remote published control state.**

That narrow definition is useful precisely because it is boring.

---

# 18. Relationship to the future Electron client

This IPC work is not merely cleanup for the current Obsidian implementation.

It is one of the prerequisites for the intended Electron client.

A tech-averse user's application should not contain logic for:

- Git plumbing;
- repository fetching;
- run persistence;
- retry rules;
- response reconciliation;
- control repository inspection.

Electron should be an interface onto AutoScribe.

It should not itself *be* AutoScribe.

With a stable IPC API, the future application can be correspondingly small:

```text
┌──────────────────────────────────┐
│ Electron                         │
│                                  │
│ Plans                            │
│ Dispatch                         │
│ Status                           │
│ Responses                        │
│                                  │
└──────────────┬───────────────────┘
               │ local IPC
┌──────────────▼───────────────────┐
│ AutoScribe service               │
└──────────────┬───────────────────┘
               │
       Git / filesystem / network
```

The same service can simultaneously support Obsidian during the transition.

That allows the UI to change without another service rewrite.

---

# 19. Recommended target architecture

The preferred near-term shape is therefore:

```text
                         REMOTE / SERVER
                               │
                 ┌─────────────┴─────────────┐
                 │                           │
          Control repository          AutoScribe pipeline
                 │                           ▲
                 │ poll/fetch                │ enqueue/reconcile
                 ▼                           │
┌───────────────────────────────────────────────────────────┐
│                    CLIENT SERVICE LAYER                   │
│                                                           │
│  Control daemon                                           │
│  ├── cached plan catalogue                                │
│  ├── current Control revision                             │
│  └── refresh state                                        │
│                                                           │
│  Dispatch service                                         │
│  ├── local validation                                     │
│  ├── inflight source state                                │
│  ├── pending dispatches                                   │
│  └── remote submission/retry                              │
│                                                           │
│  Response service                                         │
│  ├── response retrieval                                   │
│  ├── inflight candidate state                             │
│  └── writeback safety/reconciliation                      │
│                                                           │
│                Local versioned IPC API                    │
└───────────────────────────┬───────────────────────────────┘
                            │
              ┌─────────────┼───────────────┐
              │             │               │
              ▼             ▼               ▼
           Obsidian      Electron          asc
```

The important part of this diagram is not whether there are literally three Unix processes.

The important part is that there are three clearly bounded responsibilities behind one stable client API.

---

# 20. Recommended sequence

The architecture can be introduced incrementally.

### First

Define the IPC envelope and establish a single local socket.

Implement:

```text
system.ping
system.status
```

### Second

Introduce the Control service and move plan discovery behind:

```text
plans.list
plans.status
plans.refresh
```

Change Dispatch Run so opening the dialog never calls `asc` or the network.

This provides an immediate UX improvement and exercises the IPC design on a relatively harmless read-only subsystem.

### Third

Move dispatch itself behind:

```text
dispatch.create
dispatch.status
```

At that point the existing dispatcher-side `asc` call can disappear.

### Fourth

Move the response lifecycle behind:

```text
responses.list
response.inspect
response.write
```

This is the more sensitive migration and should happen after the protocol has been exercised by plans and dispatch.

### Fifth

Make `asc` itself use the IPC service for client-side operations.

That removes duplicate execution paths.

---

# Conclusion

The current absence of IPC around dispatch and response writeback is now more than a cosmetic implementation issue.

Those operations sit exactly at the architectural boundary AutoScribe is trying to establish: user interfaces on one side, authoritative service behavior on the other.

The temporary `asc` subprocess call has been useful because it allowed the service architecture to evolve without prematurely designing an application protocol. Its usefulness should now be taken as evidence that a real protocol is warranted, not as a reason to retain the shell boundary.

A small Unix-socket NDJSON API is sufficient.

The proposed third Control daemon is a particularly good first consumer of that API. It can keep the published plan catalogue hot in memory, tolerate intermittent connectivity, and make `Dispatch Run` instant without confusing cached presentation state with authoritative execution state.

The resulting rule is simple:

**No user interface should perform AutoScribe service work directly.**

Obsidian, Electron, and `asc` should all express AutoScribe operations through the same local service contract.

That boundary will matter more, not less, as the UI gets simpler.