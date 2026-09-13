# AutoScribe Follow-on Work Order

**Date:** 2026-09-05  
**Basis:** `HANDOFF.md` from the completed Rust service repair  
**Primary repository:** `/home/jeremy/Work/Loom`  
**Service:** `/home/jeremy/Work/Loom/platform/service`  
**New canonical Pandoc data directory:** `/home/jeremy/Work/Loom/platform/pandoc`

## Objective

Continue from the repaired-but-uncommitted AutoScribe service state and complete the next bounded integration pass:

1. Move the complete Pandoc data tree from `/home/jeremy/Work/Extensions/pandoc` to `/home/jeremy/Work/Loom/platform/pandoc`, making it a sibling of `service`.
2. Update all service-side references, tests, and documentation that still assume the old Pandoc location.
3. Repoint the user's Pandoc data-directory symlink to the new canonical tree.
4. Add `start-autoscribe` and `stop-autoscribe` commands to `~/.functions.zsh` that manage all current client- and server-side AutoScribe daemons.
5. Add a companion `status-autoscribe` command so daemon state can be checked from the same lifecycle interface.
6. Finish the production validation that was deferred in the preceding repair, including dispatch observation.
7. Remove or quarantine obsolete path assumptions and reduce the chance of rollback artifacts being committed accidentally.
8. Leave the resulting source changes reviewed and ready for commit, but **do not commit unless the user separately authorizes a commit**.

---

## Starting state to preserve

The previous repair established the following architecture. Do not regress it while performing this work:

- UI-independent services.
- No Obsidian activity observer.
- No legacy Unix-socket signalling.
- Git post-commit attention drives dispatch.
- One central client SQLite database.
- One persistent Worker and one persistent SQLite connection per daemon.
- Dispatch failures retain attention and use bounded persistent retry.
- Responses perform one global pending-export query per cycle and back off when idle.
- Repository and response-route failures are isolated.
- Failed exports remain unreceipted.
- Source-slug mismatch is a hard failure before writes or receipts.
- Raw source YAML frontmatter and response whitespace are preserved.
- The daemon must never mutate `master`, the user's index, or user working files.
- Rust knows only the source filepath and associated plan; document extraction remains in Pandoc.
- Git operations performed by the agent must go through the existing `git.py` wrapper.

Canonical Git wrapper:

```text
/home/jeremy/Documents/Codex/2026-09-04/files-mentioned-by-the-user-autoscribe/work/git.py
```

For read-only Git status/diff operations use `GIT_OPTIONAL_LOCKS=0`.

The canonical service source is:

```text
/home/jeremy/Work/Loom/platform/service
```

The recovered and Trash trees remain forensic evidence only and must not be built, installed, copied over the canonical source, or treated as authoritative.

---

## Critical Pandoc constraints

The Pandoc relocation is a **data ownership/path migration**, not a change to the dispatch contract.

Retain all of the following:

- Invoke `pandoc` bare.
- Do not hard-code `/home/jeremy/Work/Loom/platform/pandoc` into the Rust Pandoc command.
- Do not add `--data-dir`.
- Keep defaults and Lua-filter references relative.
- Keep exactly two defaults files in the dispatch invocation:
  1. the static extraction/emission defaults;
  2. the per-dispatch private runtime defaults in `/tmp`.
- The static defaults must continue to resolve through Pandoc's normal user data-directory behavior.
- The corrected static defaults reference must remain:

```yaml
filters:
  - emit/dispatch_calls.lua
```

or the exact equivalent already present in the validated file. Do not restore the obsolete `filters/emit/dispatch_calls.lua` path if the current validated Pandoc layout relies on Pandoc's `filters/` fallback.

---

# Phase 0 — Read-only provenance and state inventory

Before any write:

1. Read all applicable `AGENTS.md`, project context, repository instructions, `README.md`, and `CONTRACTS.md`.
2. Record:
   - `/home/jeremy/Work/Loom` branch and HEAD;
   - Loom working tree status;
   - `/home/jeremy/Work/Extensions` branch, HEAD, and status;
   - current installed `/home/jeremy/.local/bin/svc` SHA-256;
   - current `~/.local/share/pandoc` symlink target;
   - current AutoScribe systemd unit files and their states;
   - current `~/.functions.zsh` path, permissions, and syntax state.
3. Recheck actual daemon states rather than relying on the aged handoff state.
4. Inventory **all** current AutoScribe daemon units before writing lifecycle functions. Do not assume names from memory.
5. Search for old Pandoc-location references at minimum in:
   - `/home/jeremy/Work/Loom/platform/service`;
   - the rest of `/home/jeremy/Work/Loom` where relevant;
   - `/home/jeremy/Work/Extensions`;
   - `~/.config/systemd/user`;
   - AutoScribe environment/config files;
   - `~/.functions.zsh`.
6. Specifically search for:
   - `/home/jeremy/Work/Extensions/pandoc`;
   - `Work/Extensions/pandoc`;
   - obsolete `/home/jeremy/AutoScribe/extensions/pandoc`;
   - `dispatch.yaml`;
   - `filters/emit/dispatch_calls.lua`;
   - `AUTOSCRIBE_EXTENSIONS_DIR`;
   - explicit Pandoc data-dir arguments.
7. Determine whether `AUTOSCRIBE_EXTENSIONS_DIR` is still required for non-Pandoc functionality. Do **not** remove or rename it merely because Pandoc is moving.

Report the inventory before the first destructive step.

---

# Phase 1 — Move Pandoc data into Loom

## 1.1 Destination

The canonical target is:

```text
/home/jeremy/Work/Loom/platform/pandoc
```

It must be a sibling of:

```text
/home/jeremy/Work/Loom/platform/service
```

The complete Pandoc data tree should live in the Loom repository after this migration.

## 1.2 Pre-move verification

Before copying or deleting anything:

1. Verify that `/home/jeremy/Work/Extensions/pandoc` is the live source currently reached through `~/.local/share/pandoc`.
2. Verify the corrected `defaults/dispatch.yaml` is present in that source.
3. Verify the real Lua filter required by `dispatch.yaml` exists.
4. Inventory the complete tree and record hashes for regular files.
5. Check whether `/home/jeremy/Work/Loom/platform/pandoc` already exists.
6. If it exists, compare it with the source. Do not blindly overwrite divergent data.

## 1.3 Cross-repository move

Because the source and destination are in different Git repositories, treat the move as a verified copy followed by source deletion rather than pretending it is a single Git rename.

Required sequence:

1. Create `/home/jeremy/Work/Loom/platform/pandoc`.
2. Copy the source tree while preserving file bytes and permissions.
3. Compare source and destination recursively.
4. Verify file hashes match.
5. Run the isolated real-Pandoc extraction test against the **new** destination through the user Pandoc data-directory mechanism.
6. Only after successful comparison and extraction validation, remove the old `/home/jeremy/Work/Extensions/pandoc` tree.
7. Recheck both Git working trees so the intended Loom additions and Extensions deletions are obvious.

Do not leave two competing canonical Pandoc trees after successful migration.

## 1.4 User Pandoc data-directory link

Change:

```text
/home/jeremy/.local/share/pandoc
```

from:

```text
/home/jeremy/Work/Extensions/pandoc
```

to:

```text
/home/jeremy/Work/Loom/platform/pandoc
```

Requirements:

- Verify the current symlink is the expected object before replacing it.
- Preserve enough information to restore the previous target if rollback is needed.
- Replace the symlink itself; do not dereference it and copy data into `~/.local/share`.
- Verify with `readlink`/`readlink -f` after replacement.

## 1.5 Service references

Audit and update every service-side reference whose meaning changed because Pandoc moved.

This includes, as applicable:

- Rust source;
- tests and fixtures;
- `README.md`;
- `CONTRACTS.md`;
- installation notes;
- test commands;
- comments that claim Pandoc lives in Extensions;
- path assertions or test scaffolding;
- any environment lookup that was used solely to find Pandoc data.

Do **not** convert relative Pandoc defaults/filter references into absolute paths.

If Rust currently contains no absolute Pandoc-data path, preserve that design and update only stale assumptions/documentation/tests.

## 1.6 Repository ownership documentation

Document clearly that:

```text
platform/
├── service/
└── pandoc/
```

are sibling runtime components in the Loom repository.

The documentation should distinguish:

- `platform/service`: Rust service/daemon implementation;
- `platform/pandoc`: Pandoc defaults, filters, and related dispatch extraction assets.

The purpose is to make ownership obvious so Pandoc is not later moved back into the generic Extensions repository by accident.

---

# Phase 2 — Add unified daemon lifecycle commands

Edit:

```text
~/.functions.zsh
```

Add:

```text
start-autoscribe
stop-autoscribe
status-autoscribe
```

`status-autoscribe` is an intentional addition to the requested start/stop pair because the previous incident required repeated manual daemon-state checks.

## 2.1 Discover the daemon set first

Before implementing the functions, identify the authoritative current set of:

- client-side AutoScribe daemons;
- server-side AutoScribe daemons;
- whether each is a user unit or system unit;
- any required ordering/dependencies.

Do not hard-code guessed historical unit names.

Use the installed unit files and current architecture as authority.

If some server-side daemons are on a remote host:

- use an already-established canonical SSH alias or service helper if one exists;
- do not embed credentials;
- do not invent a hostname;
- do not create a new remote-management mechanism as part of this work order.

If no existing canonical remote management path exists, report that specific gap rather than silently pretending `start-autoscribe` controls remote services.

## 2.2 Start ordering

`start-autoscribe` should:

1. start required server-side daemons first;
2. verify they entered an acceptable active state;
3. start client-side daemons;
4. show a concise final status summary;
5. return non-zero if any required daemon failed to start.

It should use service-manager commands, not spawn raw daemon binaries directly.

It must be safe to run when some or all daemons are already active.

## 2.3 Stop ordering

`stop-autoscribe` should:

1. stop client-side daemons first so no new client work is submitted during backend shutdown;
2. then stop server-side daemons;
3. show a concise final status summary;
4. return non-zero if a required daemon cannot be stopped.

It must be safe to run when some or all daemons are already stopped.

Do not use broad `pkill`, `killall`, process-name matching, or PID scraping when systemd owns the services.

## 2.4 Status command

`status-autoscribe` should display the state of the same daemon set without changing it.

Prefer compact output suitable for routine terminal use, while still making failed/inactive units obvious.

Do not make a status check write service state.

## 2.5 Shell quality requirements

- Preserve the existing style of `~/.functions.zsh`.
- Avoid duplicated unit lists across the three functions where a small shared helper/array is clearer.
- Quote paths and arguments correctly.
- Do not bake secrets or tokens into the file.
- Do not add `sudo` unless existing system-level units genuinely require it.
- If system units do require privilege escalation, use the existing host convention rather than storing credentials.
- Run `zsh -n ~/.functions.zsh`.
- Load the file in a clean shell context sufficient to prove all three functions are defined.
- Test idempotent status/start/stop behavior during the controlled validation phase.
- Restore the daemon state that existed immediately before lifecycle testing unless the user explicitly requests a different final state.

Before editing `~/.functions.zsh`, create a timestamped backup outside the repository or otherwise preserve a rollback copy.

---

# Phase 3 — Configuration cleanup and path audit

After the Pandoc move and function changes:

1. Search again for the old paths:
   - `/home/jeremy/Work/Extensions/pandoc`;
   - `/home/jeremy/AutoScribe/extensions/pandoc`.
2. There should be no live service/configuration dependency on either old Pandoc path.
3. Historical rollback documentation may still mention an old path if it is clearly labelled as historical evidence. Do not rewrite forensic records merely to make grep output empty.
4. Recheck for explicit `--data-dir` usage. The service must not gain one.
5. Recheck that dispatch still uses exactly two defaults files.
6. Recheck all defaults/filter references are relative.
7. Verify the temporary runtime defaults file still carries dispatch-specific input filepath and plan slug rather than moving those values into static config.
8. Audit `AUTOSCRIBE_EXTENSIONS_DIR`:
   - retain it if other runtime components still use it;
   - remove or narrow it only if the audit proves it is now obsolete;
   - any removal must include tests and documentation proving no remaining dependency.
9. Ensure no systemd unit unnecessarily points directly at the old Pandoc directory.

---

# Phase 4 — Protect rollback artifacts from accidental commits

The previous handoff notes that `.autoscribe-install-backups` contains durable rollback material and may appear as untracked content.

Check whether the Loom repository already ignores:

```text
.autoscribe-install-backups/
```

If it does not, add the narrowest appropriate ignore rule so installation backups cannot be accidentally staged into the source repository.

Do not delete the rollback directory.

Do not broaden the ignore rule in a way that hides legitimate source files.

Also verify that `/tmp/autoscribe-repair-review` remains temporary evidence only and is not copied into the repository.

---

# Phase 5 — Build and offline validation

After source/config changes:

1. Run formatting/diff checks.
2. Run the complete offline debug test suite.
3. Run the complete offline release test suite.
4. Preserve the previously validated release-build approach unless the repository now specifies a newer canonical command.

Reference command from the preceding repair:

```sh
CARGO_TARGET_DIR=/tmp/autoscribe-repair-target \
/home/jeremy/.cargo/bin/cargo test --release --offline \
--manifest-path /home/jeremy/Work/Loom/platform/service/Cargo.toml
```

Acceptance floor: all existing 19 tests must still pass unless legitimate new tests increase the count.

Add or update tests where necessary for path assumptions introduced by this work.

No test may require mutation of the user's `master`, index, or working source files.

---

# Phase 6 — Real Pandoc validation after relocation

Run a real Pandoc extraction using the relocated data directory and normal Pandoc lookup behavior.

The expected invocation form remains:

```sh
pandoc --defaults=dispatch.yaml --defaults=<runtime-defaults-file>
```

Requirements:

- run from an isolated temporary working directory;
- use an isolated input;
- use a private runtime defaults file;
- confirm output is complete NDJSON;
- confirm expected source identity;
- confirm expected plan slug;
- confirm expected extracted content;
- do not invoke `asc enqueue` merely to prove extraction;
- do not pass an absolute filter path;
- do not pass an explicit data directory.

Also verify:

```text
~/.local/share/pandoc -> /home/jeremy/Work/Loom/platform/pandoc
```

is sufficient for production-style resolution.

---

# Phase 7 — Lifecycle-function validation

Using the authoritative daemon inventory from Phase 0:

1. Record the pre-test state of every managed daemon.
2. Run `status-autoscribe`.
3. Run `stop-autoscribe`.
4. Verify all managed local daemons are stopped and no unmanaged process was killed.
5. Run `stop-autoscribe` a second time to prove idempotency.
6. Run `start-autoscribe`.
7. Verify required server-side services start before dependent client-side services.
8. Run `start-autoscribe` a second time to prove idempotency.
9. Run `status-autoscribe`.
10. Confirm failures are visible and produce non-zero status where appropriate.
11. Restore the pre-test service state unless this work order is being used as the explicit instruction to resume production operation.

If remote server daemons are legitimately included, validate them through the existing approved remote management path only.

---

# Phase 8 — Complete deferred production daemon validation

The previous repair completed production observation for Responses but deferred Dispatch.

After the relocated Pandoc path and lifecycle commands pass validation:

1. Recheck installed binary hash.
2. Start Dispatch through the proper service manager/lifecycle function.
3. Observe Dispatch for at least two minutes.
4. Observe Responses concurrently.
5. Review both invocation journals.
6. Record:
   - aggregate CPU;
   - restart counts;
   - subprocess activity;
   - database reopen activity if measured;
   - unexpected Git activity;
   - invocation errors.
7. Preserve the prior health guard:
   - stop the affected daemon after three consecutive 10-second windows above 25% of one CPU core;
   - or after sustained sampled subprocess activity above 20 per 10 seconds;
   - or on restart/exit indicating instability.
8. Confirm idle Responses still settles to approximately the intended backoff behavior.
9. Confirm Dispatch does not return to continuous polling or obsolete activity observation.
10. Confirm failures preserve attention and retry rather than disappearing.

The prepared monitor from the previous repair may be reused only after reading it and confirming its assumptions still match the current unit names and paths:

```text
/tmp/autoscribe-repair-review/monitor-rollout.py
```

If that temporary file no longer exists, recreate only the minimal monitoring needed from the documented guard; do not depend on temporary evidence being durable.

---

# Phase 9 — Regression checks on protected user state

Before calling the work complete, explicitly verify that the new work did not alter the core write-safety guarantees.

At minimum verify:

- no daemon mutation of `master`;
- no unintended index changes;
- no unintended working-file changes;
- no receipt written for failed response routing;
- source-slug mismatch still fails before extraction/writeback;
- raw frontmatter remains byte-preserved;
- response whitespace remains preserved;
- post-commit attention generations still prevent an old acknowledgement from deleting newer attention.

Where existing automated tests already prove these properties, cite the tests and add only the smallest extra manual check needed.

---

# Phase 10 — Final repository review

Produce a final review before any commit.

## Loom repository

Expected intentional changes may include:

- existing uncommitted Rust repair files;
- `platform/pandoc/**` added;
- service path/documentation/test changes required by the Pandoc migration;
- a narrow `.gitignore` change for `.autoscribe-install-backups/` if needed;
- the follow-on work order/handoff if intentionally retained.

## Extensions repository

Expected intentional changes may include:

- deletion of the old `pandoc/**` tree.

There should not be an unexplained second canonical Pandoc copy.

## User configuration

Expected intentional changes:

- `~/.local/share/pandoc` points to the Loom platform Pandoc directory;
- `~/.functions.zsh` contains the new lifecycle functions.

Review diffs carefully.

Do not stage:

- `.autoscribe-install-backups/**`;
- `/tmp` evidence;
- unrelated user changes;
- forensic Trash/recovered trees.

---

# Rollback requirements

Maintain a bounded rollback path for this follow-on work.

Before writes, preserve:

1. the current `~/.local/share/pandoc` symlink target;
2. a backup of `~/.functions.zsh`;
3. enough source-tree information to reverse the cross-repository Pandoc move;
4. the existing service repair rollback artifacts.

If the Pandoc relocation fails before the old source is removed:

- restore the old symlink target;
- remove only the incomplete new destination after verifying it is the migration copy.

If failure occurs after the Extensions source has been removed:

- restore the source from the verified Loom copy or repository state;
- restore the old symlink target if reverting the migration.

If lifecycle-function validation fails:

- restore the backed-up `~/.functions.zsh`;
- restore daemon states to the recorded pre-test state.

Do not restore the pre-migration SQLite recovery copy over a live ledger merely as part of this work. It remains a recovery artifact requiring separate state review.

---

# Acceptance criteria

The work is complete only when all of the following are true:

- [ ] Canonical service source remains `/home/jeremy/Work/Loom/platform/service`.
- [ ] Canonical Pandoc data is `/home/jeremy/Work/Loom/platform/pandoc`.
- [ ] `service` and `pandoc` are siblings under `platform/`.
- [ ] The old `/home/jeremy/Work/Extensions/pandoc` tree is no longer a competing live canonical copy.
- [ ] `~/.local/share/pandoc` resolves to `/home/jeremy/Work/Loom/platform/pandoc`.
- [ ] Service code contains no new absolute Pandoc data-dir or filter-path resolution.
- [ ] Bare `pandoc` invocation is retained.
- [ ] Relative defaults/filter references are retained.
- [ ] Exactly two dispatch defaults files are retained.
- [ ] Static defaults and runtime defaults retain their separate responsibilities.
- [ ] Real Pandoc extraction succeeds through normal user data-directory lookup.
- [ ] All existing service tests pass in debug and release/offline mode.
- [ ] `start-autoscribe` exists and manages the authoritative daemon set.
- [ ] `stop-autoscribe` exists and manages the same daemon set.
- [ ] `status-autoscribe` exists and reports the same daemon set.
- [ ] Lifecycle commands are idempotent and return useful non-zero failure status.
- [ ] Start ordering brings server dependencies up before clients.
- [ ] Stop ordering stops clients before server dependencies.
- [ ] `~/.functions.zsh` passes `zsh -n`.
- [ ] Deferred Dispatch production observation is completed successfully.
- [ ] Responses remains healthy during concurrent Dispatch observation.
- [ ] No CPU/subprocess runaway reappears.
- [ ] No legacy socket/activity-observer behavior reappears.
- [ ] Master/index/working-file safety guarantees remain intact.
- [ ] Rollback artifacts are not accidentally stageable in Loom.
- [ ] Old live Pandoc path references are eliminated or clearly historical only.
- [ ] Loom and Extensions diffs contain only intended changes.
- [ ] No commit has been made without explicit user authorization.

---

# Final report

Return a concise completion report containing:

1. exact Loom and Extensions repository states;
2. final Pandoc symlink target;
3. files moved/changed;
4. daemon units managed by the three shell commands;
5. exact lifecycle-command behavior and ordering;
6. debug/release test counts;
7. real Pandoc extraction result;
8. Dispatch and Responses production CPU/restart/subprocess observations;
9. any remaining references to the old Pandoc paths and why they remain;
10. any retained use of `AUTOSCRIBE_EXTENSIONS_DIR` and what still needs it;
11. protected-state regression result;
12. whether the changes are ready to commit;
13. an explicit statement that no commit was made unless separately authorized.
