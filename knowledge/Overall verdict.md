I reviewed the actual Rust in `service.tar(9).gz` against the **new system-wide, UI-agnostic worker** shape: one process, transient working memory, master read-only, `autoscribe/inflight` machine-owned, cheap integrity checks, dispatch through `asc enqueue`, and response reconciliation through the export interface.

The good news is that the code is much closer to that architecture than the bundled README suggests. I would **not do another wholesale rewrite**. Most of the code has a defensible purpose. There are, however, a handful of things I would remove or reshape.

## Overall verdict

I would divide the service into four conceptual responsibilities:

1. **System worker lifecycle** — one worker, one lock, repeated passes.
2. **Vault integrity/index** — know what files/slugs exist and catch obvious mistakes cheaply.
3. **Dispatch reconciliation** — notice explicit dispatch state in Git, freeze source bytes to inflight, Pandoc them, call `asc enqueue`.
4. **Response reconciliation** — discover completed responses, reconstruct response candidates from the frozen source, save them to inflight.

That is a coherent daemon.

The biggest remaining architectural problem is **vault discovery/configuration**. The binary still expects vaults passed on the command line or through `AUTOSCRIBE_VAULTS`. That is transitional plumbing, not the final system-worker shape.

------

# `main.rs` — daemon shell

| Function                | Verdict               | Why it exists                                                |
| ----------------------- | --------------------- | ------------------------------------------------------------ |
| `main()`                | **KEEP / SIMPLIFY**   | Correct place for process startup, configuration, lock acquisition and worker launch. It should eventually start the system worker without requiring a manually supplied vault list. |
| `WorkerLock::acquire()` | **KEEP**              | Absolutely justified. We explicitly want **one system-wide daemon**, and this prevents two copies competing over the same vaults/inflight refs. |
| `WorkerLock::drop()`    | **KEEP**              | Cleans up the PID lock automatically on normal exit. Appropriate lifecycle plumbing. |
| `take_flag()`           | **REMOVE eventually** | Exists only for the current `svc worker --once` / `svc scan` CLI interface. Fine during development, but not part of the eventual daemon architecture. |
| `env_vaults()`          | **REPLACE**           | This is the clearest old-shape remnant. A system worker should discover/configure its repository population rather than require `AUTOSCRIBE_VAULTS`. |

`svc scan` is still useful as a **diagnostic command**, so I would not necessarily eliminate the one-pass capability. I would just stop making that CLI mechanism define how the production daemon knows which repositories exist.

------

# `worker.rs` — actual service

## Worker lifecycle

### `Worker::new()`

**KEEP, but change vault acquisition.**

It correctly:

- canonicalizes Git roots;
- deduplicates them;
- creates an **in-memory** database;
- establishes the `asc`, Pandoc and filter dependencies.

The only wrong part is that its caller supplies a static `Vec<PathBuf>`.

The final shape should probably make the worker own something equivalent to a **repository registry/discovery source**, then add/remove vault sessions as repositories appear/disappear.

### `Worker::database()`

**KEEP for diagnostics.**

It only exposes the transient state store so `scan --once` can print a summary. Harmless and useful.

### `Worker::startup()`

**KEEP.**

This is exactly where the startup checks we discussed belong:

- populate the complete file/slug picture;
- perform integrity checks;
- reconcile existing Git state;
- check pending exports.

Importantly, this means restarting the daemon does not rely on old process memory.

### `Worker::run()`

**KEEP.**

The perpetual system-worker loop belongs here.

### `Worker::pass()`

**KEEP.**

This is a good high-level definition of one iteration:

> scan → reconcile dispatches → reconcile responses.

That is refreshingly simple.

------

# Vault/index integrity functions

These are all defensible under the new architecture.

### `scan_all()`

**KEEP.**

Coordinates integrity scanning across all repositories and performs the global duplicate-slug test.

The **global** scope is important: copying a slugged Markdown file from Vault A to Vault B must still be detected.

### `scan_vault()`

**KEEP.**

This is the main incremental scanner.

It distinguishes:

- first observation;
- dirty working-tree Markdown;
- Markdown changed between observed master HEADs;
- deleted files.

That is precisely the cheap working-memory maintenance the daemon should do.

It does **not commit master**, which is essential.

### `check_neighbor_dir()`

**KEEP.**

This implements the cheap heuristic we discussed:

> if several neighbouring Markdown files have slugs and one suddenly does not, flag it.

This is exactly the sort of inexpensive hygiene a persistent worker should perform.

### `once_only_duplicate_check()`

**KEEP.**

Very specifically justified by your “lazy copy/paste” case.

When a newly observed/changed file has a slug, it runs an `rg` across the managed working trees to make sure another copy isn't already present.

Good place for it.

### `missing_slug_neighbors()`

**KEEP.**

This is the startup/full-scan equivalent of `check_neighbor_dir()`.

The duplication is legitimate:

- `missing_slug_neighbors()` operates cheaply over the already-built startup scan;
- `check_neighbor_dir()` narrowly checks a changed directory during incremental operation.

I would not combine them merely for neatness.

------

# Dispatch reconciliation

### `reconcile_dispatches()`

**KEEP, with one architectural proviso.**

This is the dispatcher state machine.

It:

1. finds dispatch-bearing commits;
2. extracts the plan/documents;
3. resolves exact source versions;
4. guarantees the inflight snapshot exists;
5. remembers source lineage;
6. checks Git to recover from daemon restart;
7. calls enqueue only if necessary;
8. writes a submission event into inflight.

That is strong architecture.

The proviso is that it currently assumes the **master commit trailer is the durable dispatch trigger**. If that is still our intended explicit-user-command interface, this is excellent because it is completely UI-independent.

Nothing here requires Obsidian.

### `ensure_inflight_snapshot()`

**KEEP.**

One of the most important functions in the entire service.

Before network/Pandoc/pipeline activity it guarantees that the **exact source bytes being dispatched are permanently represented in the inflight ref**.

That preserves provenance and makes response reconstruction reliable.

### `submit_dispatch()`

**KEEP / tighten interface.**

It correctly:

- blocks redispatch where unexported responses already exist;
- creates a detached worktree at the **exact master commit**;
- builds calls there;
- invokes `asc enqueue`;
- removes the worktree.

This is the correct separation:

> master supplies immutable input; machine processing happens somewhere else.

The detached worktree is especially defensible. It prevents some dirty edit in the user's live vault from leaking into a dispatch.

### `build_calls()`

**KEEP.**

This is legitimate client/service responsibility because the local machine owns:

- source files;
- Pandoc;
- source metadata extraction.

It verifies the emitted slug and prevents empty content before handing anything to the pipeline.

This function also keeps the pipeline boundary narrow: the service sends the already-defined call object to `asc enqueue`.

------

# Response side

### `poll_exports()`

**KEEP / perhaps rename `reconcile_exports()`.**

Architecturally important.

It:

- gets the pipeline's pending outputs;
- finds which vault/source they belong to;
- recovers the exact dispatched source from inflight;
- verifies the slug;
- combines the response with the original frontmatter;
- marks the candidate for review;
- saves that candidate to inflight;
- records the receipt with the pipeline.

That implements the boundary we wanted:

> daemon owns inflight; user-facing code later decides what happens to master.

There is **no direct master write here**. Good.

I would rename it because it is doing substantially more than “polling”.

------

# Markdown/source helpers

### `scan_markdown()`

**KEEP.**

Efficient `rg --files` inventory. Appropriate.

### `frontmatter_slug()`

**KEEP.**

Basic core primitive.

### `markdown_frontmatter_value()`

**KEEP for now.**

Simple frontmatter lookup without dragging a YAML parser through every cheap filesystem scan.

I would keep it intentionally narrow rather than turn the daemon into an Obsidian metadata parser.

### `preserve_frontmatter()`

**KEEP.**

Response bodies should not be permitted to casually replace authoritative document metadata.

### `set_document_review_metadata()`

**KEEP.**

This encodes the response contract that machine-produced candidate output is a **review candidate**, not silently accepted content.

That policy belongs in the service's response-materialization boundary.

------

# Dispatch/Git interpretation helpers

### `dispatch_commits()`

**KEEP if commit trailers remain the dispatch trigger.**

It reads `master`; it does not alter it.

One thing I would improve later: scanning all matching history every pass is conceptually simple but eventually inefficient. The Git inflight receipts give enough information to optimize without introducing persistent SQLite cursors.

### `dispatch_trailers()`

**KEEP.**

Clean machine-level parser for:

- one plan;
- one or more documents.

It doesn't know anything about Obsidian. Exactly right.

### `safe_dispatch_part()`

**KEEP.**

Pure identifier sanitization.

### `source_records_at()`

**KEEP.**

Captures path + blob + bytes from the exact dispatch commit. Core provenance plumbing.

### `resolve_slug_at()`

**KEEP.**

Critical because document **identity is the slug**, not the current filepath.

It deliberately resolves within the historical Git commit, which is correct.

### `resolve_slugs_in_tree()`

**KEEP.**

Similar job for a detached worktree used during Pandoc processing.

This apparent duplication with `resolve_slug_at()` is justified because they operate on different representations:

- Git object database;
- checked-out filesystem tree.

### `dirty_markdown_paths()`

**KEEP.**

Needed for cheap incremental checks of uncommitted files.

### `changed_markdown_paths()`

**KEEP.**

Needed when master advances so the daemon doesn't rescan the whole vault.

------

# `asc` boundary helpers

### `pending_export_slugs()`

**KEEP, assuming command spelling matches the final `asc exports` API.**

The responsibility is definitely correct: ask the pipeline what outputs are awaiting local materialization.

### `extract_slug()`

**KEEP, same qualification.**

Extracting completed results is a legitimate service/pipeline boundary.

### `first_string()`

**KEEP.**

Small defensive JSON compatibility helper.

If the export schema becomes rigid later, we can replace it with typed deserialization.

### `run_asc()`

**KEEP.**

One subprocess boundary wrapper is better than scattered arbitrary shell calls.

### `ndjson()`

**KEEP.**

The enqueue transport is NDJSON, so serialization belongs here.

------

# Git recovery helpers

These are particularly important because **SQLite is intentionally ephemeral**.

### `inflight_snapshot_for_dispatch()`

**KEEP.**

Allows state reconstruction after daemon restart.

### `response_snapshot_for_result()`

**KEEP.**

Prevents rematerializing the same result merely because process memory was lost.

### `dispatch_submitted_in_git()`

**KEEP.**

Also crucial.

This is what lets Git—not SQLite—remain the durable truth about whether a dispatch crossed the enqueue boundary.

### `git_log_match()`

**KEEP.**

Common primitive supporting that restart recovery.

### `git_blob()`

**KEEP.**

Tracks file identity cheaply without inventing another hashing scheme.

### `git_text()`

### `git_bytes()`

**KEEP.**

Small controlled Git wrappers.

------

# `db.rs` — the daemon's working memory

This is architecturally acceptable precisely because:

```text
Connection::open_in_memory()
```

There is **no persistent service database here**.

I would therefore stop thinking of this module as “database storage”. It is effectively the worker's **structured RAM**.

I might eventually rename it `state.rs`, but I would not replace it just because it uses SQLite. SQL views make some of the global consistency queries remarkably simple.

### `Database::memory()`

**KEEP.**

Directly implements the transient-memory requirement.

### `Database::migrate()`

**KEEP, perhaps rename `initialize()`.**

There isn't really a migration in the normal persistent-database sense; it creates the in-memory schema on every process startup.

### `connection()`

**KEEP internal.**

Low-level access used by state-query helpers.

### `worker_event()`

**KEEP, low priority.**

Useful runtime introspection.

### `vault_event()`

**KEEP.**

Stores observed HEADs and therefore enables incremental scanning.

### `file_seen()`

### `file_removed()`

**KEEP.**

Together they produce the worker's live picture of each vault.

### `latest_vault_head()`

**KEEP.**

Needed for incremental Git diffs.

### `active_files()`

**KEEP.**

Current filesystem model.

### `route_slug()`

**KEEP.**

Very important response-routing function: given a returned slug, locate its unique vault/source and dispatch lineage.

### `duplicate_slugs()`

**KEEP.**

Core global integrity query.

### `integrity_event_seen()`

### `integrity_event()`

**KEEP.**

These suppress repetitive warnings within a daemon lifetime while still recording detected problems.

### `dispatch_event()`

### `dispatch_source()`

### `dispatch_event_seen()`

**KEEP.**

Transient convenience state for the current process. Durable dispatch truth remains Git, which is the important distinction.

### `response_event()`

**KEEP.**

Same reasoning for response processing.

### `snapshot()`

**KEEP as diagnostic only.**

Very useful for `svc scan`.

### `storage()`

**KEEP.**

Error translation helper.

------

# `git.rs` — durable machine history

This module has perhaps the strongest architectural justification of all.

### `root()`

**KEEP.**

Canonical repository boundary.

### `head()`

**KEEP.**

Reads master/working repository state; does not mutate it.

### `append_inflight_snapshot()`

**KEEP. Essential.**

Creates machine-owned immutable provenance without touching master.

### `append_response_snapshot()`

**KEEP. Essential.**

Stores response candidates in inflight.

### `append_dispatch_event()`

**KEEP.**

Makes the important submission transition recoverable without persistent daemon storage.

### `read_version()`

**KEEP.**

Needed to reconstruct the exact source associated with a response.

The remaining private functions—

- `repository_root()`
- `safe_relative_path()`
- `ref_component()`
- `one_line()`
- `revision()`
- `optional_revision()`
- `git()`
- `git_status_output()`
- `temporary_index_path()`
- `git_with_env()`
- `hash_bytes()`
- `commit_tree()`
- `command_error()`
- `text()`
- `io()`

—are all **KEEP**.

They are not separate architectural features. They are defensive plumbing that lets the four public Git operations work without checking out or modifying master.

In particular, the temporary-index + `commit-tree` approach is exactly what we want: machine commits can be constructed on `autoscribe/inflight` without disturbing the user's index or working tree.

------

# `pandoc.rs`

### `run_parallel()`

**KEEP.**

Good separation. Documents are independent, Pandoc is relatively expensive, and parallel execution is bounded.

### `execute()`

**KEEP.**

One Pandoc subprocess implementation hidden behind `run_parallel()`.

No UI concerns have leaked in here.

------

# `types.rs`

These aren't functions, but I checked them because they tell us what concepts Rust believes exist.

### Keep

- `DispatchId`
- `PlanId`
- `CommitId`
- `LedgerSource`
- `LedgerSnapshotRequest`
- `LedgerSnapshot`
- `VersionRequest`
- `PandocJob`
- `PandocOutcome`

They are all concepts actually present in the new architecture.

Nothing here talks about windows, Obsidian, plugins, Electron, hotkeys or vault UI state.

Good.

------

# `error.rs`

Most is fine, but this is one place I would actually prune.

### `ServiceError::{InvalidInput, Conflict, Io, Storage}`

**KEEP.**

All meaningful.

### `ServiceError::Network`

**REMOVE unless something actually uses it.**

Network activity has deliberately been pushed behind `asc`; the Rust service should not grow its own HTTP/network layer.

### `ServiceError::NotImplemented`

**REMOVE.**

This is scaffold residue.

### `stub()`

**REMOVE.**

Definitely scaffold residue. There should be no stub API left in this codebase.

`Display`, `Error`, and `ServiceResult` obviously stay.

------

# What I would change now

I therefore **wouldn't attack the worker internals**. I would make a fairly small cleanup/refactor:

1. **Replace static `vaults: Vec<PathBuf>` startup configuration with system-worker repository discovery/registration.** The worker should be able to notice vaults appearing and disappearing instead of having its universe frozen at process start.
2. **Keep the in-memory SQLite.** It is doing exactly what we wanted Rust's working memory to do; it is not being mistaken for durable state.
3. **Keep Git as recovery truth.** `inflight_snapshot_for_dispatch`, `dispatch_submitted_in_git`, etc. are why a daemon restart doesn't matter.
4. **Delete `NotImplemented`, `Network`, and `stub()`.**
5. **Update or delete the README/CONTRACTS immediately.** They describe a substantially obsolete service: `watch-dispatch`, per-vault foreground watchers, durable SQLite cursor state, `.autoscribe/plans`, etc. At this point the documentation is more misleading than the Rust.
6. **Verify the exact `asc export/exports` command vocabulary** against the newly refactored pipeline. The architectural boundary is right; I would just make sure the Rust isn't carrying yesterday's CLI names.

And, importantly, **I found no Electron code and no Obsidian API dependency in the Rust source**. The current service is genuinely UI-agnostic. Even the commit-trailer dispatch mechanism is plain Git, so an Obsidian macro, CLI command, another editor, or future GUI could create the triggering commit without the daemon caring.

I couldn't run `cargo check` in this sandbox because Rust/Cargo isn't installed here, so this was a source/architecture review rather than a compilation test.