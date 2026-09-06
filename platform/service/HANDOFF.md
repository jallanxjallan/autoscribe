# AutoScribe Rust service repair handoff

Date: 2026-09-05 (Asia/Jakarta)
Status: installation completed; staged production validation partially completed.
The user has explicitly delayed further testing. Do not resume testing or change
service states until the user resumes the work. No commits have been made.

## Last verified runtime state

- Responses: active/running, PID 175054, zero restarts at the end of its 125-second observation. It was left running.
- Dispatch: stopped. The host execution approval for starting and monitoring it was declined before execution; it was not started.
- These are last verified states, not a fresh status check. No further checks were run after the user requested the delay.
- Installed binary: `/home/jeremy/.local/bin/svc`.
- Installed SHA-256: `dd967a9853c21179a4c9f0e70e5dcf4152ebb73e4df1daf7e8043da2dce4587d`.
- Old binary SHA-256: `75fc681708e9da1c47493bd69fbe493f7837245a0f97ebea44cda6c6c2e07dde`.
- `client.env` is unchanged. Existing systemd unit files were not modified.

## Canonical source and working changes

Service directory: `/home/jeremy/Work/Loom/platform/service`.
Containing repository: `/home/jeremy/Work/Loom`, branch `main`, HEAD
`1e13a6b67f1ecc77172bba0c70b97ce083f9b7b2`.
Remote origin: `git@github.com:jallanxjallan/autoscribe.git`.
The recovered and Trash trees are forensic evidence only.

Uncommitted service changes are in:

- `src/daemon.rs`
- `src/db.rs`
- `src/worker.rs`
- `src/main.rs`
- `src/pandoc.rs`
- `tests/core.rs`
- `README.md`
- `CONTRACTS.md`

This handoff is an additional uncommitted file. Rollback artifacts are in the
existing `.autoscribe-install-backups` directory; several appear as untracked
files and should not accidentally be included in a source commit.

Extensions repository: `/home/jeremy/Work/Extensions`, last checked HEAD
`9bd628867186f27f51aca9591c9e53b80bca1228`.
Its only repair edit is `pandoc/defaults/dispatch.yaml`.

## Implemented repair

- One persistent Worker and one central client SQLite connection per daemon;
  retained repository registration state, without editor activity observation.
- Dispatch failures retain attention, including Pandoc/enqueue failures that
  previously were logged and swallowed. Persistent retry delays are 1, 2, 4,
  8, 16, 32, then 60 seconds, capped at 60 seconds and measured after failure.
- Additive attention columns: `generation`, `failures`, `next_attempt_ms`.
  Restart recovery preserves retry deadlines. Acknowledgment of an old
  generation cannot delete newer post-commit attention.
- Responses fetch pending exports once globally. Empty results cause no
  repository scans or Worker reconstruction. Idle/failure scheduling backs off
  to 30 seconds; successful response work resets the delay to one second.
  Unchanged export-ready sets cause no SQLite row writes.
- Repository construction/processing and individual response-route errors are
  isolated. Failed exports remain unreceipted.
- Removed obsolete continuous worker loop, activity scoring/expiry, and confirmed
  unused database helpers. Historical schema and snapshot keys remain intact.
- Response source-slug mismatch fails before extraction, response events, Git
  writes, or receipts. Raw source YAML frontmatter and response whitespace are
  preserved. Dispatch source mismatch also fails before inflight writes.
- Read-only Git status suppresses optional index refresh writes.

## Architectural constraints to retain

- UI-independent services; no Obsidian activity observer or legacy socket signalling.
- Git post-commit attention drives dispatch.
- One central client SQLite database.
- Never mutate master, the user's index, or user working files.
- Rust knows source filepath and associated plan; extraction stays in Pandoc.
- Bare `pandoc` by default, relative defaults/filter references, exactly two
  defaults files: static extraction machinery and private runtime values.
- No Rust filter-path resolution or explicit data-directory override.
- Preserve raw frontmatter; slug mismatch at ingest/writeback is a hard failure.
- All agent Git operations go through `git.py`; use pathlib and preserve NDJSON contracts.

The available Git wrapper is:
`/home/jeremy/Documents/Codex/2026-09-04/files-mentioned-by-the-user-autoscribe/work/git.py`.
It execs `/usr/bin/git` with its supplied arguments. Use `GIT_OPTIONAL_LOCKS=0`
for read-only status/diff checks. Read applicable AGENTS/context files before
future changes.

## Applied Pandoc configuration repair

Verified the target directory and real Lua filter existed before changing configuration.

- `/home/jeremy/.local/share/pandoc` now points to
  `/home/jeremy/Work/Extensions/pandoc`.
- Previous link target: `/home/jeremy/AutoScribe/extensions/pandoc` (missing).
- `/home/jeremy/Work/Extensions/pandoc/defaults/dispatch.yaml` now uses
  `emit/dispatch_calls.lua` instead of `filters/emit/dispatch_calls.lua`.
  Pandoc's data-directory filter fallback already searches beneath `filters`.

Real Pandoc 3.1.6.1 extraction passed with the actual production defaults,
isolated input/output, and this invocation from `/tmp/autoscribe-repair-review`:

```sh
pandoc --defaults=dispatch.yaml --defaults=production-pandoc-runtime.yaml
```

The output was a complete NDJSON call with the expected source identity, plan,
and content. No `asc` or enqueue operation was invoked for this extraction test.

## Validation completed

- Offline debug tests: 19 passed.
- Offline optimized/release build and tests: 19 passed (15 unit, 4 integration),
  with no reported compiler warnings.
- Release build command:

```sh
CARGO_TARGET_DIR=/tmp/autoscribe-repair-target /home/jeremy/.cargo/bin/cargo test --release --offline --manifest-path /home/jeremy/Work/Loom/platform/service/Cargo.toml
```

- Installed binary came from `/tmp/autoscribe-repair-target/release/svc` and its
  installed bytes were hash-verified against that validated artifact.
- Final service diff matched the previously reviewed patch; diff and formatting
  checks passed before installation.
- Tests cover bounded retries, persistence across database reopen/migration,
  concurrent attention, successful recovery, missing repositories, source
  mismatch, frontmatter bytes, and unchanged master/index/working-file bytes.
- Isolated 65-second syscall measurement: one database open per daemon; no
  database reopen or SQLite pwrite64 after two seconds. Responses made seven
  global empty-export queries with 32 registered roots and no Git work.

## Production responses observation

Started UTC: `2026-09-05T00:45:26.687288+00:00`.
Duration: 125.002 seconds.
Aggregate unit CPU: 3.868365 seconds.
Average: 3.095% of one CPU core.
Highest 10-second window: 17.158% (startup).
Observed subprocesses: nine `asc export list-pending` calls; no other child
commands observed. Polling settled to approximately 30-second spacing.
Zero restarts and no invocation-journal errors were found.

CPU comes from systemd unit counters and includes child CPU. Subprocesses were
sampled every 20 ms through cgroup membership and `/proc`; these counts are
observations, not an exact fork/exec trace. Host ptrace_scope was 1.

Health guard used: stop the affected daemon after three consecutive 10-second
windows above 25% of one core, after sustained sampled subprocess activity above
20 per 10 seconds, or on restart/exit. No guard fired.

## Outstanding work, only when the user resumes

1. Recheck actual unit states and installed hash because the above state may age.
2. With renewed authorization to continue testing, start dispatch and observe
   aggregate unit CPU and subprocess activity for at least two minutes. Continue
   watching responses while dispatch runs. Stop an affected daemon if sustained
   excessive activity returns.
3. Review both invocation journals and report errors and measured states.
4. Do not commit unless explicitly authorized.

The prepared monitor is `/tmp/autoscribe-repair-review/monitor-rollout.py`.
Its `dispatch` mode checks the prior responses report, starts dispatch, monitors
for 125 seconds, and also checks responses CPU. Read it before use. The prior
attempt to execute dispatch mode was declined and never ran; there is no
completed dispatch rollout report.

## Rollback inventory

Manifest: `/home/jeremy/Work/Loom/.autoscribe-install-backups/service-repair-20260905-074228-manifest.json`.

- Previous binary: `/home/jeremy/Work/Loom/.autoscribe-install-backups/service-repair-20260905-074228-svc`
- Previous static defaults: `/home/jeremy/Work/Loom/.autoscribe-install-backups/service-repair-20260905-074228-dispatch.yaml`
- Previous symlink object: `/home/jeremy/Work/Loom/.autoscribe-install-backups/service-repair-20260905-074228-pandoc-link`
- Pre-migration SQLite recovery copy: `/home/jeremy/Work/Loom/.autoscribe-install-backups/service-repair-20260905-074228-service.sqlite`

Copies of the old binary/defaults were hash-verified; the saved symlink target
was verified. Both daemons were stopped when the ledger backup was taken.
Stop both daemons before restoring binary/configuration. Use atomic sibling-file
replacement for the executable and restore the saved symlink without dereferencing
it. Restoring the old link recreates its formerly broken state. Do not overwrite
a live ledger with the pre-migration backup after new work without reviewing
that state; it is a recovery copy, not an automatic rollback step.

## Evidence files (temporary artifacts)

Under `/tmp/autoscribe-repair-review`:

- `repair.diff`, `service-rollout.diff`, `pandoc-rollout.diff`
- `tests.txt` (debug test output; release outcome recorded in rollback manifest)
- `measurements.json` and `measure-*/trace.log`
- `production-pandoc-validation.json`, `production-pandoc-output.ndjson`,
  `production-pandoc-stderr.txt`
- `responses-rollout.json`, `responses-rollout-journal.txt`
- `ROLLOUT.md`, `monitor-rollout.py`

Temporary artifacts may disappear on cleanup/reboot. This handoff and the
rollback manifest/backups are durable workspace files.
