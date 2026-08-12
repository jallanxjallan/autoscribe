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
payload bytes, attempts, results, file/run associations, notices, and cache
metadata. Domain modules own meanings; `db` only provides persistence.

## `events`

- `publish(sink, notice)` — in: notice sink and typed notice; out: persisted
  notice sequence number.
- `list_since(sink, sequence)` — in: last sequence seen; out: later notices.

Every command first publishes `Accepted`, then later `Completed`, `Failed`, or
`NeedsDecision`. This supports immediate feedback in any frontend.

## `git`

- `inspect(repo, paths)` — in: repository and file paths; out: tracked/dirty
  state for each path.
- `commit(repo, request)` — in: paths, message, and commit purpose; out: commit
  identity.
- `tag_dispatch(repo, request)` — in: commit, plan, and dispatch identity; out:
  created tag.
- `read_version(repo, request)` — in: file and revision; out: exact bytes.
- `restore_version(repo, request)` — in: guarded restore request; out: new
  commit preserving the prior head in history.

## `shadow`

- `sync_for_dispatch(request)` — in: document and shadow-tree locations; out:
  ordered chunks, hashes, and sentinel mappings used to assemble a call.
- `apply_response(request)` — in: returned chunks plus expected base hashes;
  out: files changed and conflicts. It must refuse an unsafe overwrite.
- `verify(request)` — in: source document and shadow tree; out: missing,
  changed, and orphaned chunks without modifying either side.

Synchronization is command-driven. No watcher or document daemon is implied.

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

- `prepare(request)` — in: selected files and plan identity; out: persisted
  dispatch identity, exact payload, and initial `Prepared` state.
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
- `preview_write(request)` — in: selected result and current Git/shadow state;
  out: proposed writes and conflicts without modification.
- `write(request)` — in: confirmed preview token; out: writeback commit and
  changed-file links. It rechecks the preview assumptions before writing.

## `reconcile`

- `run(request)` — in: optional dispatch/file scope; out: discrepancies among
  SQLite, Git, shadow files, and the remote pipeline.
- `apply(decision)` — in: one explicit reconciliation decision; out: updated
  state and audit record.

Reconciliation reports ambiguity; it does not silently invent state.

## `dashboard`

- `overview()` — in: none; out: counts and summaries of pending uploads,
  dispatches, expected responses, failures, and recovery decisions.
- `file_state(path)` — in: file path; out: Git, shadow, dispatch, and response
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
