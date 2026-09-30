# AutoScribe server

Current live-tested server snapshot: 30 September 2026.

AutoScribe uses Python for the trusting execution core and Rust services for deterministic ingress/egress boundaries.

## Repo flow

1. A client pushes an eligible Markdown commit carrying `Plan: <label> <pln_...>` to `master` on a bare server repository.
2. The repository `post-receive` hook invokes Rust `srv-input`, which reads the committed source and signs a return route.
3. `asc enqueue` records the call and the Python executor/worker pipeline produces a response.
4. `asc export` pokes `responsed` through its Unix datagram socket; the poke carries no work payload.
5. `responsed` derives pending work from the ledger in call-ULID order and passes each full response to Rust `srv-output`.
6. Rust validates the signed return baggage and emits an authenticated effect. Repo effects are applied by `srv-writeback`; direct-mode Dropbox effects are applied by `srv-export`.
7. Repo responses are committed body-only to `autoscribe-output`, never back to server `master`.
8. After a successful Rust receipt, `responsed` stores the forensic receipt in Redis and records the export fact in SQLite.

The local client is responsible for merging an `autoscribe-output` body into the corresponding clean `master` file, preserving human frontmatter and updating the human-readable AutoScribe processed date.

## Services

The active Python user services are:

- `autoscribe-executor.service`
- `autoscribe-worker.service`
- `autoscribe-responses.service`

The former Python dispatch daemon is retired; repo ingress is owned by the Rust service hook.

Rust boundary services live in the separate `jallanxjallan/services` repository and are installed under `/opt/autoscribe/services/current/bin`.
