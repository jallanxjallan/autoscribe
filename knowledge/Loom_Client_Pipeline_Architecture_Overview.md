---
title: Loom Client and Pipeline Architecture Overview
subtitle: Review baseline for client/service/pipeline boundaries
date: 2026-08-20
status: architecture-review
audience:
  - project documentation
  - external code review
---

# Loom Client and Pipeline Architecture Overview

## 1. Purpose of this document

This document describes the current and intended architecture of the Loom/AutoScribe production system, with particular emphasis on the boundary between:

1. the Obsidian frontend;
2. the local Rust service;
3. the remote Python pipeline;
4. supporting document-processing code such as Pandoc and Lua filters.

It is intended both as durable project documentation and as a code-review brief. The central question for reviewers is not merely whether individual functions work, but whether **responsibilities are located on the correct side of each process and language boundary**.

The architecture is deliberately converging on a small number of hard rules:

- **Obsidian does Obsidian.**
- **Rust owns the local machine and local policy.**
- **Python owns remote execution and orchestration.**
- **Lua/Pandoc perform document transformations, not workflow policy.**
- **Slugs are authoritative workflow identity.**
- **Frontend components trust service state rather than reconstructing it.**
- **JSON/NDJSON is the process-boundary contract.**

The long-term objective is to make the current Obsidian frontend replaceable by a Node.js/Electron frontend without changing the local service or the remote execution model.

---

# 2. Review scope and current transition state

The system is presently in an architectural cleanup phase. The codebase contains some historical paths that are being retired.

The current canonical client-side Rust package is:

```text
platform/service/
├── Cargo.toml
├── src/
└── tests/
```

The current Obsidian control package is:

```text
platform/client/obsidian/control/
├── config/
├── macros/
├── scripts/
├── templates/
└── queries/
```

The remote execution package is Python and lives under:

```text
platform/pipeline/src/asc/
```

The current Rust service already owns substantial local policy including dispatch, writeback, Git operations, SQLite state, Pandoc invocation, pipeline calls, and result handling.

However, several older frontend/service paths remain transitional. Reviewers should particularly watch for:

- frontend filesystem discovery;
- frontend Git-derived decisions;
- direct frontend calls to `asc`;
- path-based workflow identity where a slug should suffice;
- duplicate implementations under `macros/` and `scripts/ui/`;
- old feeder-related code;
- obsolete client-side instruction persistence;
- synchronous reconciliation being performed on ordinary read or dispatch operations.

These should be treated as architectural debt, not as desired design.

---

# 3. High-level architecture

```text
┌────────────────────────────────────────────┐
│ FRONTENDS                                  │
│                                            │
│ Current: Obsidian / JavaScript             │
│ Future:  Electron / Node.js                │
│                                            │
│ Responsibilities:                          │
│ - display state                            │
│ - inspect Obsidian in-memory metadata      │
│ - collect user choices                     │
│ - edit notes / annotations / templates     │
│ - send slugs + user-entered values         │
│ - render service responses                 │
└───────────────────────┬────────────────────┘
                        │
                        │ typed JSON / NDJSON
                        ▼
┌────────────────────────────────────────────┐
│ LOCAL SERVICE — Rust                       │
│                                            │
│ Responsibilities:                          │
│ - local authority                          │
│ - slug resolution                          │
│ - filesystem access                        │
│ - Git                                      │
│ - SQLite                                   │
│ - catalogue/cache state                    │
│ - plan persistence                         │
│ - instruction synchronization              │
│ - Pandoc conversion                        │
│ - dispatch construction                    │
│ - pipeline transport                       │
│ - response retrieval                       │
│ - writeback                                │
│ - reconciliation / status                  │
└───────────────────────┬────────────────────┘
                        │
                        │ typed records / NDJSON
                        ▼
┌────────────────────────────────────────────┐
│ REMOTE PIPELINE — Python                   │
│                                            │
│ Responsibilities:                          │
│ - control records                          │
│ - Redis identity/state                     │
│ - enqueue validation                       │
│ - runtime materialization                  │
│ - queues                                   │
│ - orchestration                            │
│ - workers / engines                        │
│ - scrivener / composition                  │
│ - ledger                                   │
│ - results / export                         │
└───────────────────────┬────────────────────┘
                        │
                        ▼
              model / script / RAG engines
```

Pandoc and Lua sit alongside this flow as transformation tools:

```text
source document
    ↓
Pandoc
    ↓
Lua filters where required
    ↓
normalized structured text / AST
    ↓
Rust service / Python pipeline
```

Lua is not intended to become an independent application tier.

---

# 4. Architectural principle: many languages, one authority per responsibility

The system uses several languages because they are suited to different jobs:

| Language / environment | Intended jurisdiction |
| --- | --- |
| JavaScript in Obsidian | UI, workspace, editor, metadata already loaded by Obsidian |
| Rust | local policy, durable state, files, Git, transport, integrity |
| Python | remote pipeline, orchestration, runtime execution, Redis models |
| Lua | Pandoc filters and deterministic document transformation |
| Node.js / Electron | future frontend runtime only |

The project should resist cross-boundary duplication.

Bad architectural signals include:

```text
Obsidian JS deciding Git state
Obsidian JS walking the filesystem for workflow discovery
Obsidian JS resolving durable workflow paths
Rust understanding Obsidian-specific UI behavior
Python reaching back into a local Obsidian vault
Lua making dispatch or editorial workflow decisions
Node.js duplicating Rust service policy
```

The preferred rule is:

> A language boundary should normally coincide with a responsibility boundary.

---

# 5. Identity model

## 5.1 Slug is the authoritative workflow identity

The canonical identity of a Loom record is its top-level `slug`.

Examples:

```text
cnt.example
ctx.project-context
rol.line-editor
ins.financial-language-review
plan.fact-check
```

Paths are not durable workflow identity.

A file may be renamed or moved without changing its logical identity. Therefore the frontend should not send a path where a slug can identify the record.

The desired service request is:

```json
{
  "documents": [
    "cnt.one",
    "cnt.two"
  ],
  "plan": "plan.copy-edit"
}
```

not:

```json
{
  "documents": [
    "/home/user/project/Contents/One.md"
  ]
}
```

## 5.2 A file without a slug is intentionally invisible to workflow operations

This is a feature.

The system does not attempt to infer workflow membership from directory location or filename.

If a file has no valid top-level slug, service-side workflow discovery should not see it.

## 5.3 Resolution belongs to service

The local service resolves:

```text
slug
  ↓
rg against top-level slug declarations
  ↓
exact unique current file
```

Missing slugs and duplicate slugs are hard errors.

The frontend may use a current Obsidian `TFile` or path for opening a note in the UI, but should not treat that path as durable service identity.

---

# 6. Obsidian frontend responsibilities

Obsidian is an adapter, not the application authority.

Its legitimate responsibilities include:

- reading the active note;
- reading metadata already loaded in Obsidian's metadata cache;
- accessing current selections;
- displaying modal or panel UI;
- opening a note;
- moving or creating a note through Obsidian APIs;
- applying templates;
- editing frontmatter through the Obsidian environment;
- inserting annotations, directives, callouts, or editorial marks;
- rendering local indexes and queries;
- collecting instruction, plan, file, or action choices;
- sending slugs and user-entered values to service;
- rendering the response from service.

A useful test is:

> Is this behavior specifically about presenting or manipulating the currently loaded Obsidian workspace?

If yes, it likely belongs in control.

Another test is:

> Would this operation still make sense in a future Electron client with no Obsidian vault API?

If yes, it probably belongs in Rust service instead.

---

# 7. What Obsidian must not do

The frontend should not:

- invoke Git;
- inspect Git to make workflow decisions;
- inspect SQLite;
- construct or repair durable service state;
- walk directories to discover workflow files;
- invoke `rg` for authoritative file resolution;
- upload instruction bodies;
- resolve instruction paths for pipeline use;
- infer whether a local instruction is dirty;
- infer whether server state is current;
- reconcile client and server state;
- directly call the Python `asc` command as part of normal frontend behavior;
- construct final dispatch payload internals;
- decide writeback safety;
- treat path as the durable identity of a selected record.

The governing frontend rule is:

> **Obsidian blindly trusts service state.**

This does not mean the user cannot manually request a service refresh. It means that after service responds, the frontend should not merge, reinterpret, repair, or second-guess that response.

---

# 8. Macro structure

A macro should contain its own operation-specific interaction logic.

Reusable primitives belong under `scripts/lib/`, but a macro should not merely locate and execute a similarly named UI implementation.

Preferred:

```text
macros/define-plan.js
    ├── Define Plan UI logic
    ├── collect choices
    └── generic service/config helpers
```

Not preferred:

```text
macros/define-plan.js
    ↓
scripts/ui/define-plan.js
    ↓
actual implementation
```

Generic helpers are appropriate for:

- service transport;
- config loading;
- rendering primitives;
- clipboard handling;
- metadata normalization;
- selection utilities;
- notification;
- slug utilities.

The goal is for `macros/` to be understandable as the actual frontend operation layer rather than a second router tree.

---

# 9. Rust service responsibilities

The Rust service is the local policy boundary.

The service crate currently exposes modules including:

```text
catalog
config
dashboard
db
dispatch
events
git
instruction_sync
pandoc
payloads
plan_repository
plans
publish
reconcile
response_repository
results
service
submit
sync
types
```

Its active responsibility set includes:

- SQLite-backed durable state;
- local filesystem operations;
- slug-to-file resolution;
- Git state and commits;
- Pandoc invocation;
- dispatch preparation;
- pipeline calls;
- response retrieval;
- writeback;
- instruction synchronization;
- plan persistence;
- system/status snapshots;
- reconciliation;
- event records.

The service should increasingly be usable by any frontend, not just Obsidian.

---

# 10. Service transport contract

The frontend/service boundary should use typed JSON or NDJSON.

At a process boundary:

```text
frontend object
    ↓ serialize once
JSON / NDJSON
    ↓ deserialize once
Rust typed structure
```

Within Rust, normal Rust types should be used rather than passing serialized JSON strings between internal modules.

Likewise within a future Electron frontend, ordinary TypeScript objects should be used internally and serialization should occur only at the service boundary.

The service is intended eventually to support a Unix-domain socket for persistent local frontend communication, while retaining stdin/stdout command modes for testing and shell use where useful.

---

# 11. SQLite state model

## 11.1 Plans

Client-side plans are durable JSON blobs.

A plan refers to instructions by slug.

Conceptually:

```json
{
  "slug": "plan.financial-review",
  "steps": {
    "1": {
      "kind": "llm",
      "instruction_slugs": {
        "role": ["rol.editor"],
        "context": ["ctx.hhplawfirm"],
        "task": ["ins.financial-language-review"]
      },
      "engine": "chatgpt",
      "model": "terra"
    }
  }
}
```

Instruction text is not embedded in the plan.

## 11.2 Instructions

Instruction bodies are no longer intended to be persisted as client-side authored records in SQLite.

The service may retain **state about instructions**, for example:

```text
slug
source / scope
local_hash
server_hash or server identity
dirty state
last_seen_local
last_seen_server
```

but the database is not the source of truth for instruction content.

The current architectural direction is therefore:

```text
plans table
    slug
    json_blob

instruction/cache state
    identity + synchronization metadata
    no authoritative instruction body
```

## 11.3 Future mirrored-state database

Within the next development phase, service daemons are expected to keep local and server state mirrored into SQLite.

The future steady state is:

```text
vault watcher / reconciler ─┐
                            ├──> SQLite mirror
server watcher / reconciler ┘
```

Define Plan and Dispatch Run will then become low-latency reads of that mirror.

The UI contract should not need to change when this happens.

---

# 12. Atomic daemon rule

All state-refresh daemons should be atomic.

A refresh should conceptually perform:

```text
collect candidate state
    ↓
validate complete snapshot
    ↓
BEGIN TRANSACTION
    replace/update mirrored rows
    update refresh timestamp
COMMIT
```

If collection or validation fails:

```text
ROLLBACK / do not publish
```

The previous known-good state remains visible.

A frontend should never observe a half-updated catalogue.

---

# 13. Manual refresh policy during the transition

For the time being, automatic refresh on opening Define Plan or Dispatch Run is intentionally not required.

Both screens should expose an explicit:

```text
Refresh
```

button.

Normal opening behavior:

```text
open screen
    ↓
read cached service state
    ↓
render immediately
```

No automatic server poll.

If the user cannot find an expected plan or instruction:

```text
click Refresh
    ↓
Obsidian sends current vault instruction slugs
    ↓
service performs atomic refresh/synchronization
    ↓
service returns new authoritative catalogue
    ↓
Obsidian rerenders it
```

Obsidian must not merge local records into the returned catalogue after refresh.

The manual refresh design is transitional. Later daemons can maintain the same service cache continuously.

---

# 14. Refresh timestamps and future automatic freshness checks

The service should track freshness independently for different state domains rather than maintaining one misleading global timestamp.

Examples:

```text
vault_refreshed_at
server_instructions_refreshed_at
server_plans_refreshed_at
dispatch_state_refreshed_at
```

When automatic refresh logic is introduced later, service calls may consult these timestamps.

However, the important policy is:

> Do not refresh merely because a call occurred.

Refresh should be tied to a mutation or explicit user request.

---

# 15. Instruction synchronization policy

The historical behavior allowed brute-force re-upload of local instructions whether dirty or not.

That policy is being replaced.

New desired behavior:

```text
Obsidian supplies instruction slug
    ↓
service resolves local file
    ↓
service checks known server identity/hash
    ↓
local differs?
    ├─ no  → do nothing
    └─ yes → upload instruction
             commit affected local file(s)
```

Important points:

- Obsidian does not inspect instruction content for freshness.
- Obsidian does not calculate dirty state.
- Obsidian does not upload instruction bodies.
- Only service decides whether synchronization is necessary.
- Clean instructions are not re-uploaded.
- Local synchronization commits include only affected instruction files.
- Enqueue remains the ultimate remote identity gate.

---

# 16. Enqueue as integrity gate

The pipeline enqueue path is not a synchronization mechanism.

It is a validation and execution boundary.

For every instruction slug referenced by a plan:

```text
instruction slug
    ↓
pipeline slug map / Redis identity lookup
    ↓
valid current key identity?
```

If no valid identity exists, enqueue should fail.

The system should not silently repair an identity mismatch at enqueue time.

The intended philosophy is:

> Synchronize deliberately; validate strictly; fail loudly when identity is wrong.

If a local instruction gets lost, renamed incorrectly, fails to upload, or otherwise falls out of sync, enqueue failure is preferable to executing an unintended instruction.

---

# 17. Plan Save flow

Plan Save is a mutation and therefore may synchronize dependencies.

Desired flow:

```text
user edits Define Plan
    ↓
Obsidian constructs plan object containing slugs
    ↓
send to service
    ↓
service extracts referenced instruction slugs
    ↓
check local/server synchronization state
    ↓
upload only dirty local instructions
    ↓
commit affected instruction files if required
    ↓
save plan JSON locally
    ↓
upload/update plan remotely
    ↓
update service cache
    ↓
return receipt
```

The frontend does not need instruction paths or bodies.

---

# 18. Define Plan flow

## Normal read

```text
Open Define Plan
    ↓
service define-plan snapshot
    ↓
cached catalogue
    ↓
Obsidian renders:
    - plans
    - instructions
    - roles
    - contexts
    - task/specific instructions
    - standing instructions
    - engines
    - models
    - scripts
    - RAG profiles
```

No automatic refresh should occur simply because the screen opened.

## Explicit refresh

```text
user clicks Refresh
    ↓
Obsidian collects slugs of instruction records visible in metadata cache
    ↓
send slug list to service
    ↓
service:
    - resolves local candidates
    - checks server state
    - uploads dirty instructions only
    - commits affected files where required
    - refreshes remote catalogues
    - atomically updates cache
    ↓
return authoritative catalogue
    ↓
Obsidian rerenders exactly that catalogue
```

A local record not returned by service is not to be inserted into the UI by the frontend.

---

# 19. Dispatch Run flow

The frontend contract is deliberately small:

```json
{
  "version": 1,
  "plan": "plan.example",
  "documents": [
    "cnt.one",
    "cnt.two"
  ]
}
```

The frontend supplies:

- plan slug;
- document slugs.

It does not supply:

- absolute paths;
- instruction content;
- Git state;
- pipeline keys;
- final payload records.

Desired normal flow:

```text
user selects existing plan
user selects documents
    ↓
Obsidian sends plan slug + document slugs
    ↓
service resolves document slugs
    ↓
service loads cached plan
    ↓
service performs dispatch safety checks
    ↓
Pandoc conversion
    ↓
construct upload/enqueue records
    ↓
persist dispatch lineage / inflight state
    ↓
upload calls
    ↓
enqueue
    ↓
return receipt
```

## No refresh-on-dispatch

Dispatching with a pre-existing plan is an execution operation, not a synchronization operation.

Therefore:

```text
Dispatch existing plan
    ↓
do NOT poll server
do NOT reconcile catalogues
do NOT upload instructions merely because dispatch was requested
```

If the cached state is wrong, enqueue's identity validation is allowed to fail.

## Explicit Dispatch Refresh

Dispatch Run may offer a Refresh button for the user to request synchronization before dispatch when they suspect the cached state is stale.

The button is optional user intent, not an implicit prerequisite to dispatch.

---

# 20. Document resolution in service

The service should use slug-based `rg` discovery rather than recursive directory walking.

Conceptually:

```text
rg '^slug:\s*cnt\.one$' --glob '*.md' repository
```

The resolver must enforce:

- exactly one match;
- top-level slug semantics;
- no inferred path;
- no fallback to filename;
- no "nearest" match.

A missing slug is a hard error.

A duplicate slug is a hard error.

---

# 21. Git boundary

Git belongs entirely to Rust service for application-owned operations.

The frontend may ask service to:

- inspect state;
- show history;
- create a required service-owned commit;
- checkpoint a file;
- restore or stash when part of a defined service operation.

The frontend must not:

- run Git itself;
- use Git state to infer whether dispatch is allowed;
- include unrelated user changes in service commits.

The user may independently use a normal Git plugin or Git GUI for author-controlled commits. The bespoke `Commit Files` frontend operation has therefore been deprecated.

The service should make narrowly scoped commits only where the application requires them, such as:

- dirty local instruction synchronization;
- writeback checkpoint;
- response writeback.

---

# 22. Write Responses flow

Writeback is one of the strongest examples of why policy belongs in service.

Desired/current service invariants include:

1. verify that the current target file still has the expected top-level slug;
2. if the target is dirty, commit that target alone as a checkpoint;
3. preserve current frontmatter;
4. replace the response body;
5. set review metadata, currently:
   - `status: needs-review`
   - `producer: ai`
6. commit the target alone as the writeback;
7. record the service event / SQLite lineage;
8. acknowledge or update the remote export state.

A failure for one response should not prevent independent responses from being attempted.

Partial completion should be resumable.

Obsidian's role is to request the operation and display its manifest.

---

# 23. Pandoc and Lua boundary

Pandoc belongs on the local processing boundary for document interpretation and conversion.

Appropriate responsibilities include:

- Markdown parsing;
- DOCX/ODT/HTML/EPUB conversion;
- normalized Markdown;
- AST generation;
- preservation of headings, links, tables, notes, and metadata;
- deterministic formatting transformations.

Lua filters should perform narrow, deterministic transformations over Pandoc structures.

Examples:

```text
normalize document feature
split or classify structural elements
apply output typography rules
transform known annotations
```

Lua should not decide:

- whether a run is allowed;
- which instruction is authoritative;
- whether Git is dirty;
- which plan to dispatch;
- whether server state is fresh.

---

# 24. Python pipeline architecture

The remote Python package is organized around several major subsystems.

## 24.1 Control models

Relevant modules include:

```text
asc/models/control/
    instruction.py
    plan.py
    step.py
```

These represent executable control records.

The pipeline should treat a plan as a versioned executable description referencing instruction identities rather than depending on client filesystem structure.

## 24.2 Ingest

Relevant modules include:

```text
asc/ingest/
    handlers/content.py
    handlers/instructions.py
    handlers/plan.py
    record.py
    records.py
    stream.py
```

Ingest accepts uploaded records and materializes authoritative remote state.

## 24.3 Slug map / Redis identity

Relevant modules include:

```text
asc/state/slugmap.py
asc/redis/key.py
asc/redis/model_base.py
```

The slug map connects stable logical slugs to current remote identities/keys.

This is why enqueue can make identity validation a hard invariant.

## 24.4 Enqueue

Relevant modules include:

```text
asc/enqueue/
    reader.py
    record.py
    records.py
    plan.py
    runtime.py
    job.py
    call.py
    service.py
```

Enqueue responsibilities include:

- reading submitted records;
- validating plan and instruction references;
- resolving remote identities;
- materializing runtimes;
- creating jobs/calls;
- recording failures for invalid work;
- placing executable work into the appropriate processing state.

Enqueue should not silently compensate for stale client state.

## 24.5 Runtime materialization

`asc/enqueue/runtime.py` and the process models turn a plan into executable runtime state.

A runtime combines:

```text
plan step
+ instruction references
+ call/source record
+ engine selection
+ arguments
+ optional directive
```

The pipeline, not the frontend, owns the exact runtime structure.

## 24.6 Workers

Relevant modules include:

```text
asc/worker/
    daemon.py
    execute.py
    loader.py
    runtime_io.py
    inbox.py
```

Workers execute engine calls.

Engine types may include:

- LLM/model calls;
- deterministic scripts;
- retrieval/RAG work;
- other registered transforms.

Workers consume typed runtime input and emit typed results/failures.

## 24.7 Scrivener

Relevant modules include:

```text
asc/scrivener/
    daemon.py
    execute.py
    inbox.py
```

Scrivener is a separate execution/composition stage where required by the pipeline.

The precise responsibility should remain distinct from generic worker execution and should be reviewed for overlap.

## 24.8 Orchestration

Relevant modules include:

```text
asc/orchestrator/
    daemon.py
    initiate.py
    process.py
    evaluate.py
    active.py
```

Orchestration advances work across pipeline states.

The broad lifecycle is conceptually:

```text
enqueue
    ↓
initiate
    ↓
process
    ↓
evaluate
    ↓
result / next step / completion
```

## 24.9 Ledger

Relevant modules include:

```text
asc/ledger/
    schema.py
    records/
    inspect.py
    lifecycle.py
    queries.py
    write.py
```

The ledger is the durable execution/accounting record.

It should be the authoritative source for lifecycle facts that need durable history rather than transient Redis queue state.

## 24.10 Export

Relevant modules include:

```text
asc/exporter/
    pending_exports.py
    export_result.py
    list_unexported.py
```

Export exposes completed results for retrieval/writeback and records export acknowledgement.

---

# 25. Remote execution lifecycle

A simplified end-to-end lifecycle is:

```text
LOCAL SOURCE
    ↓
Obsidian selects source slug(s)
    ↓
Rust service resolves files
    ↓
Pandoc produces normalized dispatch records
    ↓
service records lineage
    ↓
pipeline ingest/upload
    ↓
enqueue validates plan + instruction identities
    ↓
runtime materialization
    ↓
job / call queues
    ↓
worker / retrieval / script execution
    ↓
orchestrator advances plan
    ↓
result is recorded
    ↓
ledger records lifecycle
    ↓
export becomes available
    ↓
Rust service retrieves response
    ↓
safe local writeback + Git commits
    ↓
Obsidian displays reviewed result
```

---

# 26. Directive handling

A directive is ephemeral user intent attached to a particular run or source context.

The architectural direction is that directive extraction/injection belongs at the client/service preparation boundary, while the pipeline runtime receives the normalized directive as part of executable runtime data.

A directive should not become a durable instruction unless explicitly converted into one.

The distinction is:

```text
instruction
    durable reusable control

directive
    ephemeral run-specific override/input
```

---

# 27. Config-driven frontend behavior

The Obsidian control package increasingly treats YAML config under:

```text
control/config/
```

as the source of truth for:

- vocabulary;
- record classes/types;
- templates;
- paths;
- UI labels;
- workflow choices;
- protocol command names;
- maintenance/deprecation declarations.

The frontend should avoid accumulating hard-coded copies of domain vocabularies when a config file already owns them.

This rule is frontend configuration policy and should not be confused with authoritative runtime state, which belongs to service/pipeline.

---

# 28. Current deprecated or transitional concepts

The following concepts should not drive new architecture:

## Feeder

Feeder is considered retired for current design purposes.

Any remaining feeder files are legacy and should not be used as evidence for current boundaries.

## Commit Files

The bespoke Obsidian Commit Files operation is deprecated.

Author-controlled commits are better handled through standard Git tooling. Rust retains only application-owned Git operations.

## Client-side instruction bodies

Persisting authored instruction bodies in the local SQLite database is deprecated.

Plans retain instruction slugs.

## Direct `asc` frontend calls

These are transitional and should be removed from live frontend operations.

The service may still invoke the Python pipeline CLI internally until a different service/pipeline transport is introduced.

## Filesystem walking from frontend

Deprecated for workflow discovery.

## Path identity

Deprecated as an inter-process identity contract where a slug exists.

---

# 29. Future Electron / Node.js frontend

The eventual desktop frontend should be able to replace Obsidian without inheriting Obsidian-specific assumptions.

The service API should make the future frontend look like:

```text
render service state
collect choices
send slugs
receive typed response
```

Electron should not become a second service.

Node.js should not own:

- Git;
- SQLite policy;
- local reconciliation;
- instruction synchronization;
- pipeline payload construction;
- writeback safety.

Those remain in Rust.

This makes the frontend replaceable while preserving the difficult local correctness logic.

---

# 30. Near-term daemon architecture

The next client-side evolution is likely to introduce long-running Rust daemons that maintain mirrors of vault and server state.

## Vault daemon

Long-term ideal:

```text
filesystem events / inotify
    ↓
resolve changed slugs
    ↓
update SQLite mirror transactionally
```

Periodic polling remains as a reconciliation safety net.

## Server daemon

Long-term ideal:

```text
server events if available
    ↓
update server catalogue mirror
```

with periodic reconciliation polling as backup.

Suggested eventual polling behavior when events are unavailable:

```text
active state:
    vault ~3 seconds
    server ~10–30 seconds

idle:
    exponential/progressive backoff
    vault up to ~60 seconds
    server up to several minutes
```

However, these intervals are implementation tuning rather than architectural requirements.

The important invariant is atomic publication of refreshed state.

---

# 31. Mutation-driven refresh rule

Future automatic freshness logic should distinguish reads from modifications.

Read/execution call:

```text
use cached mirror
```

Mutation:

```text
check relevant refreshed_at
    ↓
refresh only if needed
    ↓
perform mutation
```

For example:

```text
dispatch existing unchanged plan
    → no server poll

save modified plan
    → synchronize relevant instruction/plan state

explicit Refresh
    → force requested reconciliation
```

This prevents the server from being polled unnecessarily merely because a user runs a stable pre-existing plan.

---

# 32. Failure philosophy

The system should prefer explicit failure over heuristic recovery at critical identity boundaries.

Examples:

```text
duplicate slug
    → fail

missing slug
    → fail

plan refers to unknown instruction identity
    → enqueue fails

writeback target identity changed
    → fail

service refresh cannot produce valid complete snapshot
    → retain previous cache
```

This is especially important because automated "helpfulness" at one layer can conceal state corruption that is much harder to diagnose later.

---

# 33. Review invariants

A reviewer should be able to audit the code against the following invariants.

## Frontend

- [ ] No Git execution from Obsidian.
- [ ] No Git-derived workflow policy in Obsidian.
- [ ] No SQLite access from Obsidian.
- [ ] No direct authoritative filesystem discovery for workflow records.
- [ ] No client-side instruction dirty detection.
- [ ] No client-side instruction-body upload.
- [ ] No direct `asc` calls in live frontend operations.
- [ ] Service requests prefer slugs over paths.
- [ ] Service responses are rendered without local reconciliation.
- [ ] Operation macros contain operation-specific UI logic rather than forwarding to same-name UI modules.

## Rust service

- [ ] All local filesystem resolution is centralized and slug-based.
- [ ] Duplicate/missing slugs are hard errors.
- [ ] Git operations include only explicitly affected paths.
- [ ] SQLite publication is transactional.
- [ ] Plans persist as JSON and reference instruction slugs.
- [ ] Instruction bodies are not treated as SQLite source-of-truth.
- [ ] Instruction synchronization uploads only dirty local records.
- [ ] Application-owned instruction synchronization commits affected files.
- [ ] Dispatch of an existing plan does not force catalogue reconciliation.
- [ ] Explicit refresh is atomic.
- [ ] Writeback is resumable across partial Git/DB/export completion.
- [ ] Service-facing structures are suitable for non-Obsidian frontends.

## Pipeline

- [ ] Ingest owns remote materialization of uploaded control records.
- [ ] Slug map is the authoritative slug → remote identity mapping.
- [ ] Enqueue validates instruction and plan identity rather than repairing it.
- [ ] Runtime materialization occurs in pipeline, not client.
- [ ] Queue/orchestrator responsibilities are distinct.
- [ ] Worker engine interfaces use typed input/output.
- [ ] Ledger remains durable lifecycle history.
- [ ] Export acknowledgement cannot accidentally lose an un-written local result.
- [ ] Failure records contain enough identity information for reconciliation.

---

# 34. Specific areas for an external code reviewer to inspect

The following areas deserve particular scrutiny.

## 34.1 Duplicate authority

Search for any instance where two layers independently decide the same thing.

High-risk examples:

```text
frontend and service both discovering instructions
frontend and service both interpreting Git state
service and pipeline both constructing plan semantics differently
SQLite cache and filesystem both treated as authoritative
```

## 34.2 Hidden path coupling

Search for:

```text
abspath
source_path
vault_path
path
```

and determine whether each use is:

- legitimate local implementation detail; or
- incorrectly crossing a process boundary as identity.

## 34.3 Direct process execution

Audit frontend code for:

```text
child_process
spawn
spawnSync
exec
asc
git
rg
```

Most of those should be absent from the frontend operation layer.

## 34.4 Filesystem walking

Audit for:

```text
readdir
walk
getMarkdownFiles
find
glob
```

Not every occurrence is wrong: Obsidian may iterate its in-memory note collection for local UI purposes.

The key question is whether iteration is being used to reconstruct authoritative workflow state that service should own.

## 34.5 State races

Inspect:

- refresh transaction boundaries;
- writeback recovery;
- simultaneous daemon refresh and foreground mutation;
- plan save during catalogue refresh;
- instruction file edited during dirty check/upload;
- dispatch using cache while a refresh is running.

Atomic cache replacement and clear transaction ownership are important.

## 34.6 Idempotency

Review:

- repeat Plan Save;
- repeat Dispatch after uncertain network result;
- repeat Write Responses after Git commit but before remote acknowledgement;
- repeat instruction synchronization;
- daemon restart during refresh.

The system should distinguish retrying the same operation from creating a new logical operation.

## 34.7 Contract drift

The system has previously accumulated consumers that guessed alternate field names or shapes.

Reviewers should reject code that compensates for unstable contracts by accepting many ambiguous forms unless backward compatibility is explicitly required.

Prefer one canonical shape and validation at the boundary.

---

# 35. Architectural end state

The desired end state is not "everything in Rust."

It is:

```text
Obsidian / Electron
    small, replaceable UI adapters
        ↓
Rust service
    single local authority
        ↓
Python pipeline
    single remote execution authority
        ↓
model / script / RAG engines
```

Supporting tools remain narrow:

```text
Pandoc → document interpretation
Lua    → deterministic Pandoc transforms
Git    → versioned local source safety
SQLite → durable local service state/cache
Redis  → remote active identity/state/queues
Ledger → durable remote execution history
```

The key design principle is:

> **Many implementation languages are acceptable; multiple competing authorities are not.**

If the boundaries remain strict, the sophistication of the client becomes manageable rather than fragile.

---

# 36. Compact code-review brief

For a reviewer who wants the shortest possible framing:

> Loom is being refactored into a thin-frontend / authoritative-local-service / authoritative-remote-pipeline architecture. Obsidian should deal only with its loaded workspace, collect slugs and user choices, and render service responses. Rust owns local files, slug resolution, Git, SQLite, synchronization, plans, dispatch construction, Pandoc, writeback, and reconciliation. Python owns remote control records, Redis identity, enqueue validation, runtime materialization, workers, orchestration, ledger, and export. Slugs—not paths—are durable workflow identity. Plans persist locally as JSON blobs containing instruction slugs. Instruction bodies are not local-DB authority. Normal dispatch of an existing plan does not trigger server reconciliation; explicit Refresh and mutation operations may. Future Rust daemons will atomically mirror vault and server state into SQLite so Define Plan and Dispatch become low-latency cache reads. The main code-review task is to identify any place where authority leaks across these boundaries or where two layers independently reconstruct the same state.
