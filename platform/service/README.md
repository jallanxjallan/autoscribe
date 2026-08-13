# AutoScribe Service Scaffold

This package fixes the boundary between AutoScribe frontends and the
client-side Rust service before implementation begins. Obsidian is the first
frontend. Electron may come later, but is not assumed anywhere in the service
contract. The package compiles, but every
operation that would touch durable state, Git, files, or the network returns
`ServiceError::NotImplemented`.

The central rule is simple: Rust owns state and policy. A frontend displays the
state supplied by Rust, collects an explicit user choice, and sends a command.
The frontend never constructs dispatch payloads, decides whether a retry is
safe, or infers the state of a run.

Obsidian is the first consumer. Its JavaScript macros should become thin
adapters that open panels, collect choices, invoke the service, and render the
returned views and notices. The Rust API must remain usable from a CLI, tests,
or a future Electron client without changing domain behavior.

## Important design decisions already represented

- SQLite is the authority for client-side service state.
- A dispatch is saved before transmission.
- A retry reuses the original dispatch identity and the exact saved payload.
- After polling, a dispatch becomes `Succeeded` or `Uncertain`; an uncertain
  dispatch waits for an explicit retry or cancel command.
- Git is the overwrite guardrail and preserves editorial second-guessing.
- SQLite holds the offline-capable sync store, including a durable outbox for
  runs that have not yet reached the pipeline and locally retained downloaded
  data. The daemon synchronizes periodically, and a frontend may request an
  immediate synchronization.
- A definitely unsent run remains pending and retryable. A run whose remote
  acceptance is unknown becomes uncertain and waits for an explicit decision.
- There is no automatic filesystem-watching daemon for document conversion.
  Dispatch and write-response commands invoke synchronization explicitly.
- Plans, models, engine metadata, instructions, runs, responses, and notices
  are exposed through Rust query functions.
- Pandoc is the sole parser and constructor for Markdown document boundaries.
  Independent Pandoc operations run as bounded parallel batches.
- Every significant action emits an immediate accepted notice and eventually a
  completion or failure notice.

## Package map

See `CONTRACTS.md` for every module and function, including its inputs and
outputs. Public request/response types live in `src/types.rs`. The orchestration
facade is `src/service.rs`; every frontend adapter should depend on that facade
rather than calling storage or domain modules directly.

`adapters/obsidian/README.md` maps the existing Obsidian surfaces to this
service boundary and states which decisions JavaScript is forbidden to make.

## Compile the scaffold

```sh
cargo check
cargo test
```

The tests confirm that the package is wired correctly and that unimplemented
operations fail explicitly rather than pretending to succeed.

## Suggested implementation order

1. `db` migrations and repositories
2. `events` notice persistence and subscription
3. `git` and offline synchronization
4. `catalog`, `plans`, and payload assembly
5. `dispatch` plus exact-payload retry
6. `results` and guarded writeback
7. `reconcile` and dashboard queries
8. Obsidian adapter transport and CLI entry points
9. Other frontend adapters, without domain changes
