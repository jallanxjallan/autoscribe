# AutoScribe client service

This crate is the client-side policy boundary. Rust owns SQLite, Git, document
resolution, Pandoc conversion, pipeline calls, and writeback. Obsidian is a
thin adapter: it sends slugs or file choices and renders returned manifests.

## Dispatch Run

Run from the vault repository and send JSON on standard input:

```json
{"version":1,"plan":"plan.example","documents":["doc.one","doc.two"]}
```

```sh
svc dispatch-run
```

Only the plan slug and document slugs cross the frontend boundary. Rust finds
each unique Markdown file by its top-level `slug`, validates the plan, invokes
Pandoc, appends the immutable inflight ledger snapshot, records SQLite lineage,
uploads calls, and enqueues the plan. Other frontmatter is filter policy, not
dispatch-script policy.

## Write Responses

Send `{"version":1}` to `svc write-responses`. The command emits one NDJSON
`writeback-result` per pending response. For each target Rust:

1. verifies that the current file still has the expected slug;
2. commits the target alone when it is dirty, as a writeback checkpoint;
3. preserves current frontmatter and replaces the body;
4. sets top-level `status: needs-review` and `producer: ai`;
5. commits the target alone as the writeback;
6. records the response event and acknowledges the export.

A failed item is reported without preventing independent responses from being
attempted. Re-running resumes a writeback that reached Git before its
SQLite/export acknowledgement.

## Other frontend operations

- `system-snapshot` returns Git and pipeline counts.
- `git-files` owns inspect, commit, history, per-file stash, and restore.
- `define-plan-snapshot`, `plan-save`, and `instructions-sync` own authored
  catalog operations.

Repository-scoped commands derive the repository from their working directory.

## Build and test outside the source tree

```sh
export AUTOSCRIBE_CARGO_TARGET_DIR="$HOME/.cache/autoscribe/cargo/service"
export CARGO_TARGET_DIR="$AUTOSCRIBE_CARGO_TARGET_DIR"
cargo test --manifest-path platform/service/Cargo.toml
cargo build --release --manifest-path platform/service/Cargo.toml --bin svc
```

The Obsidian adapter uses the same default target and honors
`AUTOSCRIBE_CARGO_TARGET_DIR`, `AUTOSCRIBE_ROOT`, and `SVC_BIN`.
