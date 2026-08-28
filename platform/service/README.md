# AutoScribe Rust service

`svc` provides command-line reconciliation plus foreground watcher processes.
There is no live Obsidian IPC requirement.

## Dispatch watcher

Run from a vault Git worktree:

    svc watch-dispatch

The watcher consumes editorial commits in branch order. A dispatch commit must
carry exactly one plan trailer and one or more document trailers:

    Editorial commit

    Autoscribe-Plan: plan.example
    Autoscribe-Document: cnt.first
    Autoscribe-Document: psg.second

Each document value is an immutable document slug. The watcher opens a detached
worktree at the marked commit, resolves each slug to its filepath within that
snapshot, saves the exact bytes on `refs/heads/autoscribe/inflight`, and only
then runs Pandoc, uploads calls, and enqueues the plan. Live working-tree paths
and edits are never used.

The branch cursor and per-commit receipts are durable in the service SQLite
database. A failed commit does not advance the cursor; the foreground watcher
reports the failure and retries it after 30 seconds. `Ctrl-C` stops the watcher.
Only one watcher may run for a vault at a time. For testing or manual polling:

    svc watch-dispatch --once

Polling defaults to two seconds. `AUTOSCRIBE_DISPATCH_POLL_MS` and
`AUTOSCRIBE_DISPATCH_RETRY_MS` override the normal and failed-pass intervals.

## Refresh

Run from a vault Git worktree:

    svc refresh

`svc refresh` also ensures `/.autoscribe/` is present in the repository-local `.git/info/exclude`, so Plan Manager drafts and Control state never appear in normal Git/Obsidian Git status.

One refresh pass:

1. builds the vault-wide slug index;
2. synchronizes changed local instructions without committing master;
3. ingests locally edited plans from `.autoscribe/plans/`;
4. refreshes the cached server catalog; and
5. atomically writes `.autoscribe/control-state.json` for Obsidian Control.

Dispatch commit scanning belongs exclusively to `watch-dispatch`; refresh does
not upload or enqueue editorial documents.

## Git boundary

AutoScribe makes no automatic commits on the editorial/master branch. Human
commits made through Obsidian Git or the normal Git CLI are authoritative.
Machine forensics live on `refs/heads/autoscribe/inflight`.

The private `__dispatch-run` command is an implementation detail used only by
`watch-dispatch` inside a detached worktree so the existing Pandoc/dispatch path
operates on the exact source commit. It is not an interactive dispatch API.

## Responses

The existing `write-responses` command remains the writeback boundary. Response
candidates are saved on the inflight ref before master is inspected. Clean,
unchanged targets may be written and are left dirty; dirty or committed-diverged
targets are left untouched and reported as decision-required.
