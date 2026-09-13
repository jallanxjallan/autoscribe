# AutoScribe Obsidian Refactor Work Order

**Date:** 2026-09-05  
**Canonical master vault:** `/home/jeremy/Work/Obsidian`  
**Purpose:** Complete the Obsidian-side cleanup after the service and vault-manager architecture changes.

## Governing principle

Prune now. Add functionality back later only when there is a demonstrated use.

The resulting architecture should be easy to explain:

```text
Obsidian
  ├─ captures user intent
  ├─ creates/reads Git state
  ├─ provides explicit writeback UI
  └─ can replay the repository post-commit hook

Git post-commit hook
  └─ gives the dispatcher attention

Rust services
  ├─ own dispatch/retry
  └─ own response retrieval
```

Obsidian must not know how service daemons are signalled, started, stopped, addressed, or implemented.

The repaired service architecture explicitly requires UI-independent services, no Obsidian activity observer or legacy socket signalling, and Git post-commit attention as the dispatch trigger.

---

# Starting assumptions

The separate `manage-vault` refactor establishes this lifecycle:

```text
Obsidian opens folder as vault
        ↓
init-vault
        ↓
one-time Git/repository setup
        ↓
update-vault
        ↓
self-contained managed vault
```

Thereafter `update-vault` propagates committed master-vault changes.

Therefore:

- project vaults are self-contained;
- `/home/jeremy/Work/Obsidian` is never a runtime dependency of a project vault;
- managed Git hooks live inside each vault and are selected through repository-local `core.hooksPath`;
- stale managed files are removed through the explicit maintenance/deprecation mechanism;
- local/project-specific files outside managed paths are not mirror-deleted.

Do not duplicate any `manage-vault` work in this refactor.

---

# High-level objectives

1. Remove all obsolete socket/IPC daemon signalling from the Obsidian package.
2. Replace Dashboard signal receipts with durable Git-derived **Unprocessed Dispatches**.
3. Add **Poke Dispatcher**, implemented only by replaying the repository `post-commit` hook.
4. Fix the stale-modal race in **Write Responses**.
5. Consolidate Git execution onto the existing shared asynchronous Git boundary.
6. Delete unused runtime modules and obsolete current-selection machinery.
7. Simplify and unify clipboard/file resolution.
8. Remove dead and pseudo-configuration.
9. Delete the complete vocabulary subsystem for now.
10. Remove obsolete Templater compatibility code from AutoScribe.
11. Keep Templater itself outside AutoScribe/update-vault policy.
12. Remove stale Control/instruction concepts from Obsidian.
13. Align docs, config validation, migration cleanup, QuickAdd wiring, and Dashboard with the resulting architecture.
14. Avoid opportunistic rewrites of working code that is merely large.

---

# Phase 0 — Read-only provenance and inventory

Before writing:

1. Read applicable `AGENTS.md`, repository context, README files, and current audit docs.
2. Record the master-vault branch, HEAD, and working-tree state.
3. Identify all uncommitted user changes and do not overwrite them.
4. Inventory `.vault-update` and the managed paths propagated by `update-vault`.
5. Inventory current QuickAdd user-script registrations and relevant hotkeys from the **live master vault**, not only from an archive.
6. Run the current config checker and record its output.
7. Syntax-check all custom JavaScript before editing.
8. Search the complete managed vault for:
   - `signal`
   - `socket`
   - `daemon`
   - `dispatch-signals`
   - `AUTOSCRIBE_DISPATCH_SOCKET`
   - `AUTOSCRIBE_RESPONSES_SOCKET`
   - `Vocabulary`
   - `vocabulary.yaml`
   - `STAGES`
   - `STATUSES`
   - `instructions.yaml`
   - `selection-state`
   - `current-selection`
   - `__obsidianCurrentSelections`
   - `query-runtime`
   - `annotation-loader`
   - `git-dashboard`
   - `templater`
   - `tp.user`
   - `<%`
   - `make_slug`
9. Search for hard-coded executable paths, particularly:
   - `/home/jeremy/.local/bin/svc`
   - `/home/jeremy/Python3.13Env/bin/asc`
10. Record the current Git-hook layout but do not modify hook behavior in this work order except for Dashboard replay support.

---

# Phase 1 — Delete obsolete daemon signalling

Delete the live signalling subsystem:

```text
_scripts/lib/daemon-signal.js
_scripts/lib/dispatch-signal.js
```

Remove all imports and consumers.

At minimum this includes:

- `_views/Dashboard.md`
- `_ui/quickadd/write-responses.js`
- `_scripts/README.md`
- `_scripts/docs/MACRO-AUDIT.md`
- root `README.md`
- `_scripts/config/protocol.yaml`
- any related validation code.

## Remove signalling state

Delete all live logic for:

```text
dispatch-signals.json
system-status/dispatch-signals.json
```

No replacement signal receipt/state file should be introduced.

A successful attempt to wake/replay processing is **not** evidence that processing happened.

## Maintenance cleanup

Add the retired signalling modules to the existing explicit deprecation list so already-materialized project vaults remove stale copies during `update-vault`:

```text
lib/daemon-signal.js
lib/dispatch-signal.js
```

Add only paths relative to `_scripts/`, consistent with the current maintenance contract.

Do not introduce generic mirror deletion.

---

# Phase 2 — Simplify `protocol.yaml`

After signalling and current-selection cleanup, audit whether `protocol.yaml` has any live consumer left.

The current file contains:

- session/current-selection protocol keys;
- step-contract argument names;
- daemon socket configuration;
- plan-cache configuration.

Current implementation evidence indicates several of these are pseudo-configuration or stale.

Delete every section with no live consumer.

If the refactor removes the final live consumer, delete `protocol.yaml` entirely and remove it from config validation/docs.

Do not preserve a configuration file merely because it might be useful later.

Do not wire currently ignored YAML keys into code merely to justify keeping them.

---

# Phase 3 — Dashboard: Unprocessed Dispatches

Replace:

```text
Unsent Dispatches
Resend signal
Dispatch signalling
```

with:

```text
Unprocessed Dispatches
Poke Dispatcher
```

## Durable source of truth

The Dashboard must derive unprocessed dispatches from Git state.

It must not use:

- signal receipt files;
- daemon state;
- sockets;
- process state;
- a new Dashboard-owned database;
- a new “poked” receipt.

Dispatch commits are commits containing the canonical trailers:

```text
Autoscribe-Dispatch: 1
Autoscribe-Plan: ...
Autoscribe-Document: ...
```

Before implementing the processed/unprocessed test, inspect the current Rust dispatcher and confirm the durable Git invariant that proves a dispatch has been incorporated into the service-managed inflight state.

Preferred implementation, **only if verified against the current service behavior**:

```sh
git merge-base --is-ancestor <dispatch-commit> refs/heads/autoscribe/inflight
```

If the dispatcher uses a different durable Git relationship, implement that exact relationship instead.

Do not invent another status protocol.

## Dashboard display

For unprocessed dispatches show useful durable data such as:

- short commit;
- plan slug;
- document slugs/count.

Do not add per-dispatch poke buttons unless there is a real dispatch-specific operation.

`Poke Dispatcher` is repository-wide, so use one section-level action.

---

# Phase 4 — Poke Dispatcher

Add a Dashboard action named exactly:

```text
Poke Dispatcher
```

Its operation is only:

```sh
git hook run post-commit
```

executed with the active vault repository as `cwd`.

Requirements:

- use the normal repository Git helper;
- respect `core.hooksPath`;
- do not execute `.git/hooks/post-commit` directly;
- do not call `svc`;
- do not call `systemctl`;
- do not open a socket;
- do not inspect daemon PIDs;
- do not record a poke receipt;
- do not create another dispatch commit;
- do not claim work was processed merely because the hook returned zero.

After successful hook replay:

1. notify the user that the dispatcher was poked;
2. reload the durable unprocessed-dispatch list.

On hook failure:

- show the actual Git/hook error;
- leave the unprocessed state untouched;
- return/display failure clearly.

Prefer disabling/hiding the button when there are no unprocessed dispatches.

---

# Phase 5 — Remove response-daemon signalling

`Write Responses` currently wakes the response daemon before reading Git.

Delete that behavior.

`Refresh` should mean exactly:

```text
read local Git/inflight state again
```

Remove:

- `daemon-signal.js` dependency;
- vault-path dependency used only for signalling;
- “Waking response daemon…” UI text.

The response-retrieval service is independent of this explicit user writeback command.

---

# Phase 6 — Fix stale-modal writeback race

This is a required safety fix.

Current behavior:

1. `listResponseCandidates()` decides which files are ready.
2. The modal remains open.
3. User files, branch, or inflight state may change.
4. `applyReadyResponses()` later trusts the stale rows.
5. It reads from the **current moving inflight ref**, while recording the older displayed inflight commit.

This can overwrite user edits or mix response generations.

## Required preflight at write time

Immediately before any file write or staging:

1. resolve repository root again;
2. verify the checked-out editorial branch is still the expected branch;
3. verify the current inflight ref still resolves to the exact snapshot commit shown/validated by the modal;
4. recompute readiness for every proposed file;
5. verify every target remains clean;
6. verify no candidate has changed from `ready` to decision-required;
7. abort the entire write if any invariant changed.

Do not partially write the subset that happens still to be clean.

Tell the user to Refresh and review again.

## Pin reads to the validated commit

Once preflight succeeds, read response bytes from:

```text
<validated-inflight-commit>:<path>
```

not:

```text
refs/heads/autoscribe/inflight:<path>
```

The commit message trailer must reference that same validated inflight commit.

## Existing safety boundaries

Preserve:

- explicit user invocation is required to write onto the editorial branch;
- only clean candidates are automatically writable;
- decision-required files remain untouched;
- externally managed `autoscribe/*` branches are never user writeback targets.

---

# Phase 7 — Consolidate Git execution

Delete the duplicate synchronous Git runner in:

```text
_scripts/lib/git-dashboard.js
```

Preferred result:

- Dashboard Git state reads use `_scripts/lib/repo.js`;
- dispatch-specific Git operations live in `_scripts/lib/git-dispatch.js`;
- response-specific Git operations remain in `_scripts/lib/git-responses.js`.

You may either:

1. delete `git-dashboard.js` and move its small state functions into a sensible existing boundary; or
2. retain `git-dashboard.js` only as an asynchronous state-composition module that delegates **all Git execution** to `repo.js`.

Do not retain a second `spawnSync("git", ...)` stack.

Dashboard refresh should not block Obsidian's renderer with synchronous Git subprocesses.

## Shared Git boundary

Extend `repo.js` only with small generic helpers actually required by the refactor.

Do not turn it into a large Git framework.

---

# Phase 8 — Delete unused selection machinery

The supplied tree contains:

```text
_scripts/selections/selection-state.js
_scripts/selections/current-selection.js
```

`selection-state.js` has no live consumer.

`current-selection.js` exports a writer but no live code in the supplied vault writes current-selection state. Dispatch Run only reads/clears it.

Given the prune-first policy:

1. verify the live master vault has no external/current Bases or Dataview code that calls `writeCurrentSelection()` or writes `__obsidianCurrentSelections`;
2. if none exists, delete both selection modules;
3. remove current-selection merging from Dispatch Run;
4. remove related `protocol.yaml` keys;
5. remove related `paths.yaml` keys;
6. remove related docs/checker references.

Afterward, Dispatch Run should use the current clipboard selection as its document selection source.

Do not preserve an unwritten session-selection protocol for hypothetical future use.

If a live external writer is discovered, report it before deleting `current-selection.js`; do not invent a compatibility layer.

---

# Phase 9 — Consolidate clipboard selection

Use `_scripts/lib/clipboard-selection.js` as the shared resolver.

## Remove wrapper

Delete:

```text
_scripts/lib/query-runtime.js
```

and have `clipboard-selection.js` use the canonical vault-path helper directly.

## Unify Compiled Notes and Compiled Synopses

`Compiled Notes.md` currently implements additional title-based resolution locally while `Compiled Synopses.md` uses the shared clipboard resolver.

Move any genuinely useful title fallback into `clipboard-selection.js`, then make both queries consume the same resolver.

Goals:

- one parser;
- one path normalization rule;
- one slug resolver;
- one title-resolution rule;
- one header-row rule.

Do not duplicate clipboard interpretation inside Dataview views.

## Simplify Add Active File

`add-active-file.js` currently has local clipboard read/write helpers and reads/parses clipboard state redundantly.

Refactor it to use the shared clipboard helpers where sensible.

Keep the operation simple:

```text
active Markdown file
  → require slug
  → preserve valid existing selection if possible
  → append slug / filename / path row
  → write clipboard
```

Do not introduce persistent clipboard-selection state.

---

# Phase 10 — Delete trivial compatibility wrappers

Delete:

```text
_scripts/lib/annotation-loader.js
```

and have its consumers load:

```text
_scripts/lib/annotate.js
```

directly.

Update:

- `_ui/quickadd/annotate-text.js`
- `_ui/quickadd/list-annotations.js`

or any other live consumer discovered during inventory.

Do not replace it with another one-function loader.

---

# Phase 11 — Delete the vocabulary subsystem

The user has explicitly chosen to remove controlled vocabulary for now because usage is still in flux.

Delete the complete vocabulary feature:

```text
_scripts/config/vocabulary.yaml
_views/Vocabulary Cheatsheet.md
_ui/quickadd/vocabulary-cheatsheet.js
```

Remove all vocabulary-specific logic from:

```text
_scripts/lib/annotate.js
_scripts/config-check.js
README files
MACRO-AUDIT.md
QuickAdd configuration
hotkeys
Dashboard/resource listings if applicable
```

Remove unused exports such as:

```text
STAGES
STATUSES
vocabularyConfig()
```

Do not replace this with a reduced vocabulary file.

Do not add the previous `open`, `needs-review`, stage, producer, action, or other values somewhere else merely to preserve them.

If future workflows need controlled vocabulary, it can be designed from actual usage then.

## Records remain descriptive, not vocabulary-enforced

Values currently used by `records.yaml` may remain literal defaults where they have a live consumer.

Do not validate them against a deleted vocabulary catalogue.

---

# Phase 12 — Remove stale Control/instruction configuration

Delete:

```text
_scripts/config/instructions.yaml
```

Remove all validation/docs that imply the Obsidian vault contains or resolves the durable Control instruction catalogue.

Current architecture:

- instructions/plans belong to Control/server-side architecture;
- Obsidian Dispatch Run selects a published plan slug;
- Obsidian does not resolve plan instruction components.

Delete old concepts such as:

- `standing`
- `rule`
- `role`
- `context`
- `task`
- `resolver_properties`

where they survive only in Obsidian configuration/docs.

Do not replace them.

---

# Phase 13 — Prune pseudo-configuration

Audit every key in the remaining YAML files against a live consumer.

Default rule:

> no live consumer → delete the key.

Do not wire unused config into code just to preserve the config.

## `workflow.yaml`

Retain the live inflight ref:

```yaml
writeback:
  inflight_ref: refs/heads/autoscribe/inflight
```

Delete currently unused:

```yaml
writeback.status
writeback.producer
slug.suffix_alphabet
slug.suffix_length
```

Slug generation is implemented by `_scripts/lib/slug.js`; there is currently no consumer of the YAML slug settings.

## `paths.yaml`

Remove stale keys after signalling/current-selection cleanup, including any no longer used:

- `current_selection_tmp`
- `system_status_dir`
- root `Dashboard.md` fallback support if represented here;
- other runtime/workflow keys with no remaining consumer.

Retain only keys used by live code.

## `queries.yaml`

Retain live definitions for:

- Compiled Notes;
- Compiled Synopses;
- Editorial Notes.

Delete unused historical sections such as:

```text
content_index
topic_index
```

unless a live managed view discovered during Phase 0 still consumes them.

## `ui.yaml`

Retain only live UI values.

The supplied tree appears to consume `missing_value` and some Editorial Notes configuration through current views.

Delete stale groups for retired:

- status filters;
- status sorts;
- file-state/history columns;
- old response tables;
- content index;
- topic index;

unless a live consumer is found.

## `dashboard.yaml`

Prune entries that exist only to suppress already-retired files once cleanup makes those entries unnecessary.

Keep the Dashboard's actual current actions and resource folders.

## `protocol.yaml`

As above: delete completely if no consumer remains.

---

# Phase 14 — Templater: remove AutoScribe compatibility, not the plugin globally

Templater is **not** an AutoScribe dependency.

Slug generation is performed by:

```text
_scripts/lib/slug.js
```

through `Set Note Type` / `applyTemplateToFile()`.

Current managed templates contain no Templater executable syntax.

## Delete Templater compatibility code

Remove the backward-compatibility parser from:

```text
_scripts/lib/apply-template-tools.js
```

that recognizes:

```text
<% tp.user.make_slug(...) %>
```

Afterward `renderString()` should support only the current intentional template substitutions, such as `{{title}}`.

Do not retain a parser for retired Templater templates.

## Keep a cheap regression guard

The config checker may retain a negative check that managed templates do not contain executable Templater syntax:

```text
<%
tp.user.
```

This is a guard against accidentally reintroducing an obsolete dependency, not a Templater runtime dependency.

## Do NOT manage Templater itself

The user will manually remove Templater from the current master vault and only active project vault.

Do **not**:

- add `.obsidian/plugins/templater` to maintenance cleanup;
- add `.obsidian/plugins/templater-obsidian` to maintenance cleanup;
- make `update-vault` purge Templater;
- globally forbid Templater;
- treat Templater installation as an AutoScribe error.

The user may later use Templater for unrelated purposes, such as a publishing-source vault.

AutoScribe should simply have no dependency on it.

---

# Phase 15 — Canonical slug path

Retain `_scripts/lib/slug.js` as the single AutoScribe slug implementation.

Retain current behavior unless a concrete bug is found:

- kebab-case body;
- configured record prefix from `records.yaml`;
- generated short random suffix;
- duplicate-slug detection helpers.

`Set Note Type` remains responsible for assigning a slug when the selected record type has a prefix.

Do not add Templater or YAML pseudo-configuration back into this path.

Update comments/docs so this ownership is explicit.

---

# Phase 16 — Simplify Dashboard opening

`_ui/quickadd/open-dashboard.js` currently falls back from:

```text
_views/Dashboard.md
```

to:

```text
Dashboard.md
```

Make `_views/Dashboard.md` the sole canonical path.

Delete the root-path fallback.

If historical root `Dashboard.md` files need removal in existing project vaults, add the correct managed/deprecation cleanup entry through the existing maintenance mechanism.

Do not keep duplicate canonical paths.

---

# Phase 17 — Plan-cache path and executable cleanup

Audit `_scripts/lib/asc-control.js` and `protocol.yaml`.

Current implementation hard-codes fallback executables such as:

```text
/home/jeremy/.local/bin/svc
/home/jeremy/Python3.13Env/bin/asc
```

and `protocol.yaml` contains plan-cache command/path values that the implementation does not consume.

Simplify to one actual implementation.

Preferred behavior:

- use `AUTOSCRIBE_SERVICE` / `AUTOSCRIBE_ASC` overrides when explicitly set;
- otherwise use bare `svc` and `asc` from the environment/PATH;
- derive XDG cache path in code if that remains the live design;
- delete ignored plan-cache pseudo-configuration from YAML.

Do not maintain two independent descriptions of the same path/command.

Keep Dispatch Run's intended behavior:

- read cached plans at modal startup;
- **Refresh plans** explicitly invokes the plan service once and rereads the cache.

Update README/audit language to match this actual behavior.

---

# Phase 18 — QuickAdd runtime bootstrap: retain and document correctly

Do **not** refactor the repeated QuickAdd `loadRuntime()` bootstrap merely to reduce repeated lines.

QuickAdd evaluates UserScripts rather than loading them as ordinary Node modules, so the entrypoint must first resolve the current vault's shared runtime to a local filesystem path with:

```js
app.vault.adapter.getFullPath("_scripts/lib/macro-runtime.js")
```

Important documentation rule:

- this is the **current self-contained vault's path**;
- it is not a runtime dependency on `/home/jeremy/Work/Obsidian`.

Do not add a master-vault absolute path.

Do not add a new bootstrap framework.

---

# Phase 19 — QuickAdd configuration ownership

Inspect the **live master vault** to determine the current canonical QuickAdd configuration file.

The supplied archive did not contain `.obsidian/plugins/quickadd/data.json`, while existing documentation describes QuickAdd wiring as master-managed.

Resolve the contradiction.

Given the established vault lifecycle, the intended rule is:

> reusable QuickAdd configuration belongs to the committed master snapshot and is materialized by `update-vault`, unless a specific setting is intentionally declared project-local.

If live QuickAdd `data.json` is the authoritative registration file:

1. ensure the correct master file is included by `.vault-update`;
2. remove stale vocabulary macro registration;
3. ensure all retained macro paths point to `_ui/quickadd`;
4. remove registrations for deleted macros;
5. verify active hotkeys point only to current commands.

If QuickAdd stores runtime-local state that should not be propagated, separate that from reusable macro wiring rather than copying arbitrary state wholesale.

Do not preserve `migrate-quickadd.js` forever merely because old paths once existed. After current vaults are migrated, treat it as transitional cleanup and remove it when no longer required.

Do not remove it in this pass if the current active vault still needs it.

---

# Phase 20 — Config checker becomes a stale-architecture guard

Refactor `_scripts/config-check.js` around the remaining architecture.

Remove checks for deleted:

- vocabulary configuration;
- instruction configuration;
- signalling protocol;
- pseudo-configuration.

Keep or add cheap useful checks:

1. every template referenced by `records.yaml` exists;
2. every managed template has valid parseable frontmatter where required;
3. no managed template contains Templater executable syntax;
4. every Dashboard action points to an existing entrypoint;
5. config files referenced by live code exist;
6. obsolete signalling modules do not exist;
7. obsolete socket/signalling keys are absent from live configuration;
8. deleted vocabulary artifacts do not reappear accidentally if a narrow stale-file check is useful;
9. canonical Dashboard exists only at `_views/Dashboard.md`;
10. retained maintenance entries are path-safe;
11. no stale `_control`/deprecated macro paths exist except in explicit migration/deprecation checks.

Do not turn `config-check.js` into a full static analyzer.

---

# Phase 21 — Documentation cleanup

Update:

```text
README.md
_scripts/README.md
_scripts/lib/README.md
_ui/README.md
_ui/quickadd/README.md
_scripts/docs/MACRO-AUDIT.md
```

as applicable.

The docs must say consistently:

## Dispatch

```text
Dispatch Run
  → creates durable dispatch commit
  → normal Git post-commit hook gives service attention
```

No socket wake-up.

If hook attention was missed:

```text
Dashboard → Poke Dispatcher → git hook run post-commit
```

## Responses

Response retrieval is independent.

`Write Responses`:

```text
read inflight Git state
  → review
  → revalidate immediately before write
  → explicitly commit clean responses
```

It does not wake the daemon.

## Plans

Dispatch Run reads the local plan cache.

**Refresh plans** runs the plan-refresh command once.

Do not say Dispatch Run directly resolves instructions or plan components.

## Vault ownership

Project vaults are self-contained after `update-vault`.

QuickAdd filesystem bootstrap resolves files inside the current vault.

## Slugs

Slugs are created by AutoScribe script code, not Templater.

## Vocabulary

Do not document a controlled vocabulary subsystem for now.

---

# Phase 22 — Avoid unnecessary refactors

Do not split or rewrite working modules merely because of size.

Specifically:

- do not split `dispatch-run.js` simply because it is long;
- do not invent a generic UI framework for its modal;
- do not replace `vault-loader.js` unless a concrete defect is found;
- do not replace the lightweight config loader merely because another YAML parser exists inside Obsidian;
- do not eliminate QuickAdd bootstrap lines by adding more abstraction than they replace;
- do not replace plain YAML/JavaScript with a new schema framework;
- do not add state databases/files for UI bookkeeping.

The target is **less code and fewer concepts**.

---

# Phase 23 — Validation

## Static

Run:

- syntax checks for every custom `.js` file;
- `config-check.js`;
- searches for stale architecture terms.

There should be no live references to:

```text
daemon-signal
dispatch-signal
dispatch-signals.json
AUTOSCRIBE_DISPATCH_SOCKET
AUTOSCRIBE_RESPONSES_SOCKET
autoscribe-dispatch.sock
autoscribe-responses.sock
Resend signal
Unsent Dispatches
Vocabulary Cheatsheet
config/vocabulary.yaml
config/instructions.yaml
selection-state.js
```

References inside explicit maintenance/deprecation guards are allowed when clearly intentional.

There should be no live AutoScribe template dependency on:

```text
<%
tp.user.
```

## Dashboard

In a disposable/current test vault:

1. load Dashboard;
2. verify repository state renders;
3. verify Dashboard refresh remains responsive;
4. create/find a known unprocessed dispatch;
5. verify it appears under **Unprocessed Dispatches**;
6. run **Poke Dispatcher**;
7. verify the normal repository hook runs;
8. verify no socket/service call occurs;
9. verify Dashboard reloads durable Git state.

## Dispatch Run

Verify:

- plan cache loads;
- Refresh plans works;
- clipboard file selection works;
- current-selection session machinery is absent if pruned;
- dispatch commit trailers are correct;
- commit invokes the repository post-commit hook normally;
- no signalling call occurs after commit.

## Write Responses race test

Required tests:

### A. Normal clean write

1. open Write Responses;
2. identify ready response(s);
3. write without intervening changes;
4. verify exact validated inflight commit was used;
5. verify local response commit trailer records that commit.

### B. User edit after modal load

1. open modal with a ready file;
2. modify that target file;
3. press Write;
4. verify the operation aborts before any response file is written/staged.

### C. Inflight advances after modal load

1. open modal;
2. advance/change inflight ref;
3. press Write;
4. verify operation aborts and requires refresh.

### D. Branch changes after modal load

1. open modal;
2. change branch;
3. press Write;
4. verify operation aborts.

### E. Mixed candidates

If any originally-ready candidate becomes unsafe, verify the entire write attempt aborts rather than partially applying a subset.

## Clipboard queries

Verify Compiled Notes and Compiled Synopses resolve the same representative clipboard rows consistently:

- path;
- absolute path inside vault;
- slug;
- title fallback;
- tab-delimited rows with headers.

Verify ambiguous title resolution fails safely rather than silently choosing the wrong file.

## Set Note Type / slug

Verify:

- record type with prefix gets one slug from `slug.js`;
- record type without prefix has no pipeline slug injected;
- no Templater execution occurs;
- current templates remain plain Markdown/frontmatter.

---

# Phase 24 — Existing active vault propagation

After the master refactor passes isolated checks:

1. commit/publish the master-vault changes only when separately authorized;
2. run the newly refactored `update-vault` in the one current active project vault;
3. verify deprecated signalling files disappear;
4. verify managed hook remains correct;
5. verify Dashboard and QuickAdd load;
6. verify no project-local content/workspace state is removed;
7. verify Templater is **not** purged by `update-vault`.

The user is handling any Templater plugin deletion manually.

---

# Suggested deletion inventory

Expected deletions, subject to live-source verification:

```text
_scripts/lib/daemon-signal.js
_scripts/lib/dispatch-signal.js
_scripts/lib/annotation-loader.js
_scripts/lib/query-runtime.js
_scripts/selections/selection-state.js
_scripts/selections/current-selection.js
_scripts/config/vocabulary.yaml
_scripts/config/instructions.yaml
_ui/quickadd/vocabulary-cheatsheet.js
_views/Vocabulary Cheatsheet.md
```

Possible additional deletion:

```text
_scripts/config/protocol.yaml
```

if no live consumer remains after signalling/current-selection removal.

Do not delete Templater plugin directories as part of this refactor/update-vault logic.

---

# Expected edits

Likely edits include:

```text
_views/Dashboard.md
_ui/quickadd/write-responses.js
_ui/quickadd/dispatch-run.js
_ui/quickadd/open-dashboard.js
_ui/quickadd/add-active-file.js
_ui/quickadd/annotate-text.js
_ui/quickadd/list-annotations.js

_views/queries/Compiled Notes.md
_views/queries/Compiled Synopses.md

_scripts/lib/repo.js
_scripts/lib/git-dispatch.js
_scripts/lib/git-responses.js
_scripts/lib/git-dashboard.js        # simplify or delete
_scripts/lib/clipboard-selection.js
_scripts/lib/apply-template-tools.js
_scripts/lib/annotate.js
_scripts/lib/asc-control.js

_scripts/config/maintenance.yaml
_scripts/config/paths.yaml
_scripts/config/queries.yaml
_scripts/config/ui.yaml
_scripts/config/workflow.yaml
_scripts/config/dashboard.yaml
_scripts/config-check.js

README.md
_scripts/README.md
_scripts/lib/README.md
_ui/README.md
_ui/quickadd/README.md
_scripts/docs/MACRO-AUDIT.md

.vault-update                    # only if managed-file inventory must change
QuickAdd/hotkey config           # live authoritative files only
```

Do not edit files just to touch them; this is an expected review set, not a mandatory churn list.

---

# Acceptance criteria

The refactor is complete only when:

- [ ] No live Obsidian code signals any AutoScribe daemon.
- [ ] No live socket names or socket environment variables remain.
- [ ] `daemon-signal.js` and `dispatch-signal.js` are deleted and deprecated for existing vault cleanup.
- [ ] Dashboard shows **Unprocessed Dispatches**, derived from durable Git state.
- [ ] Dashboard provides one **Poke Dispatcher** action.
- [ ] Poke executes `git hook run post-commit` through the repository Git boundary.
- [ ] Poke does not call `svc`, `systemctl`, sockets, or daemon PIDs.
- [ ] Poke records no fake processing receipt.
- [ ] Write Responses no longer wakes the responses daemon.
- [ ] Write Responses revalidates branch, inflight commit, and clean candidates immediately before writing.
- [ ] Response bytes are read from the exact validated inflight commit.
- [ ] A stale modal cannot overwrite an intervening user edit.
- [ ] Dashboard Git work uses the shared asynchronous Git boundary.
- [ ] No duplicate synchronous Dashboard Git subprocess layer remains.
- [ ] Unused selection-state machinery is removed.
- [ ] Current-selection machinery is removed if no live writer is found.
- [ ] Clipboard resolution is shared by Dispatch/queries where applicable.
- [ ] Compiled Notes and Compiled Synopses do not maintain divergent resolution logic.
- [ ] `annotation-loader.js` and `query-runtime.js` are removed.
- [ ] The entire vocabulary subsystem is removed.
- [ ] `instructions.yaml` and stale Obsidian instruction-resolution concepts are removed.
- [ ] Remaining config keys all have live consumers.
- [ ] `workflow.yaml` retains only live settings.
- [ ] Templater compatibility parsing is removed from AutoScribe.
- [ ] Slug generation is owned by `slug.js`.
- [ ] AutoScribe does not install, remove, or globally prohibit Templater.
- [ ] `_views/Dashboard.md` is the sole canonical Dashboard path.
- [ ] Plan-cache documentation matches implementation.
- [ ] Hard-coded user executable paths are removed in favor of environment override + PATH defaults.
- [ ] QuickAdd bootstrap remains local to the self-contained current vault.
- [ ] QuickAdd registration/hotkeys contain no deleted macro paths.
- [ ] Config checker passes and guards against signalling/Templater regressions.
- [ ] Existing active vault receives the cleanup through `update-vault` without losing project-local state.
- [ ] No unrelated service or vault-manager architecture is modified.
- [ ] No commit is made unless separately authorized.

---

# Final report

Return a concise report containing:

1. master-vault branch/HEAD and final working-tree status;
2. deleted files;
3. pruned configuration keys/files;
4. final Dashboard dispatch behavior;
5. durable rule used to determine “unprocessed” and how it was verified against the service;
6. exact Poke Dispatcher implementation;
7. Write Responses stale-state safeguards;
8. Git-layer consolidation;
9. clipboard/query consolidation;
10. current-selection decision and evidence for deletion/retention;
11. vocabulary deletion summary;
12. instruction/Control cleanup summary;
13. Templater compatibility removal and confirmation that Templater itself is unmanaged;
14. slug-generation validation;
15. QuickAdd/hotkey configuration changes;
16. config-check and JavaScript syntax results;
17. isolated functional validation results;
18. active-vault `update-vault` validation;
19. any remaining stale-looking reference and the explicit reason it remains;
20. confirmation that no commit was made without authorization.
