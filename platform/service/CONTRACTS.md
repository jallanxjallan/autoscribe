# Module and Function Contracts

All fallible functions return `ServiceResult<T>`. Until implemented, each
returns `ServiceError::NotImplemented` with its stable operation name.

## `types`

Contains identifiers, enums, commands, records, and status views shared across
modules. Inputs and outputs use owned Rust types so that an Obsidian adapter,
CLI, tests, or a later frontend can serialize them without changing service
policy.

## `config`

- `load(path)` — in: configuration-file path; out: validated `ServiceConfig`.
- `validate(config)` — in: parsed configuration; out: the same configuration
  after checking paths, endpoint settings, and timing values.

## `db`

- `open(config)` — in: database configuration; out: `Database` handle.
- `migrate(db)` — in: database handle; out: `()` after schema reaches the
  current version.
- `transaction(db, operation)` — in: database and a named logical operation;
  out: `Transaction` used to make a state transition atomic.

The database will store plans, catalog snapshots, dispatch identities, exact
payload bytes, attempts, results, file/run associations, notices, and sync
metadata. Domain modules own meanings; `db` only provides persistence.

## `events`

- `publish(sink, notice)` — in: notice sink and typed notice; out: persisted
  notice sequence number.
- `list_since(sink, sequence)` — in: last sequence seen; out: later notices.

Every command first publishes `Accepted`, then later `Completed`, `Failed`, or
`NeedsDecision`. This supports immediate feedback in any frontend.

## `pandoc`

- `run_parallel(executable, jobs, max_parallel)` — in: an absolute Pandoc
  executable path, independent jobs, and a concurrency bound; out: one typed
  outcome per job in input order.

Pandoc owns all Markdown parsing and construction at document boundaries. The
service invokes it only through batches. Multi-job batches reject a concurrency
limit below two, and one failed document does not prevent the remaining jobs
from completing. Filters, defaults, templates, and reference documents live in
the first-class `platform/pandoc` package.

## `git`

- `inspect(repo, paths)` — in: repository and file paths; out: tracked/dirty
  state for each path.
- `commit(repo, request)` — in: paths, message, and commit purpose; out: commit
  identity.
- `create_dispatch_branch(repo, request)` — in: an exact source revision,
  source branch, dispatch and plan identities, selected path/slug pairs, and
  canonical payload hash; out: an idempotently created
  `autoscribe/run/<dispatch-id>` branch and its metadata commit. Creation uses a
  temporary worktree and never switches the user's active branch. Reusing the
  branch name with different metadata is a hard conflict.
- `tag_dispatch(repo, request)` — in: commit, plan, and dispatch identity; out:
  idempotently created `autoscribe/dispatch/<dispatch-id>` tag.
- `read_version(repo, request)` — in: file and revision; out: exact bytes.
- `restore_version(repo, request)` — in: guarded restore request; out: new
  commit preserving the prior head in history.

All repository paths are validated as normalized, repository-relative paths.
Dispatch branches are durable reproducibility records; SQLite remains the
operational authority for pending, acknowledged, and uncertain delivery state.

## `sync`

- `enqueue(db, payload)` — durably inserts an immutable dispatch identity,
  exact payload bytes, and payload hash into the SQLite outbox. Re-enqueuing
  identical data is idempotent; reusing an identity for different data fails.
- `run(db, transport, request)` — attempts pending uploads, retains offline
  work, quarantines uncertain delivery, downloads available results, and
  returns synchronization counts.
- `status(db)` — returns the last successful sync time plus pending and
  uncertain outbound counts.
- `pending_payloads(db)` and `inbound(db, identity)` — expose exact queued
  payloads and locally retained downloaded results to service-core callers.

The daemon synchronizes periodically. A frontend can also request a sync, but
does not transmit or modify sync records itself. The SQLite outbox is durable
and authoritative for runs that have not been acknowledged by the pipeline;
it is not a disposable cache. This module is unrelated to the future Shadow
deployment package for chunking office documents into hidden Markdown files.
An ordinary connection failure leaves a record pending for a later automatic
attempt. A failure where remote acceptance is unknown moves it to `uncertain`;
periodic synchronization must not retry it without an explicit decision.

## `catalog`

- `refresh(request)` — in: server endpoint plus cached revision; out: updated
  model, engine, script, and instruction metadata.
- `snapshot()` — in: none; out: current locally cached catalog view.
- `resolve_instructions(request)` — in: ordered instruction references; out:
  immutable resolved instruction versions in role/context/specific order.

## `plans`

- `list()` — in: none; out: plan summaries for the UI.
- `get(identity)` — in: plan identity; out: complete immutable plan version.
- `save(draft)` — in: edited plan draft; out: saved plan identity and hash.
- `validate_for_dispatch(request)` — in: plan plus selected records; out:
  warnings or errors, including action/plan mismatches.

## `payloads`

- `build(request)` — in: selected committed files, plan, resolved
  instructions, and optional directive; out: canonical payload bytes and hash.
- `verify_saved(request)` — in: stored payload, stored hash, and dispatch
  identity; out: verified `SavedPayload`. A retry may use only this output.

Canonicalization must be deterministic. A dispatch row and its payload are
written in one transaction before any network call.

## `dispatch`

- `prepare(db, repo, request)` — in: selected path/slug pairs, plan identity
  and version, and the exact canonical payload bytes and SHA-256 produced by the
  client-side Pandoc conversion; out: the locked source revision, durable
  dispatch branch, and persisted SQLite outbox record. Dirty selected files are
  committed explicitly. Clean selected files remain valid inputs, and an
  all-clean selection creates no source commit. Unselected work is untouched.
- `transmit(identity)` — in: existing dispatch identity; out: attempt record.
  It loads the saved payload; it never rebuilds it.
- `poll(identity)` — in: dispatch identity; out: `Succeeded` or `Uncertain`
  after the configured polling interval and limit.
- `retry(identity)` — in: uncertain dispatch identity; out: new attempt for
  the same identity and exact payload.
- `cancel(identity)` — in: uncertain/prepared identity; out: `Cancelled`
  state. Cancellation means stop trying; it does not claim the server never
  received an earlier attempt.
- `status(identity)` — in: dispatch identity; out: complete dispatch view.

## `results`

- `list_pending()` — in: none; out: available results not yet written.
- `retrieve(identity)` — in: dispatch identity; out: locally persisted result
  metadata and bytes.
- `preview_write(request)` — in: selected result and current Git/sync state;
  out: proposed writes and conflicts without modification.
- `write(request)` — in: confirmed preview token; out: writeback commit and
  changed-file links. It rechecks the preview assumptions before writing.

## `reconcile`

- `run(request)` — in: optional dispatch/file scope; out: discrepancies among
  SQLite sync state, Git, local files, and the remote pipeline.
- `apply(decision)` — in: one explicit reconciliation decision; out: updated
  state and audit record.

Reconciliation reports ambiguity; it does not silently invent state.

## `dashboard`

- `overview()` — in: none; out: counts and summaries of pending uploads,
  dispatches, expected responses, failures, and recovery decisions.
- `file_state(path)` — in: file path; out: Git, sync, dispatch, and response
  state derived from authoritative sources.
- `history(path)` — in: file path; out: commits, dispatch tags, writebacks, and
  any active stash marker.

## `service`

- `start(config_path)` — in: config path; out: initialized `Service` after
  configuration validation and database migration.
- `execute(command)` — in: typed UI command; out: `CommandReceipt` immediately.
  Long work continues behind the service boundary and reports through notices.
- `query(query)` — in: typed UI query; out: typed `QueryResponse`.
- `shutdown()` — in: service handle; out: `()` after in-flight local work is
  safely checkpointed. It does not cancel remote work.

This is the only module a frontend adapter needs to call. The first adapter
will serve Obsidian; no module in this crate may depend on Obsidian, Electron,
DOM concepts, windows, panels, or JavaScript callbacks.

## Frontend adapter boundary (outside this crate)

An Obsidian adapter translates macro actions into `Command` and `Query` values,
then translates typed responses into notices, pick lists, links, and panels. It
does not inspect SQLite, call Git, assemble payloads, or decide state
transitions. A future Electron adapter can perform the same translation against
the unchanged service facade.
