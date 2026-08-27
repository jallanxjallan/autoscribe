# AutoScribe Obsidian Control

Control is the Obsidian-facing UI. It does not own Git history and it does not
maintain a live connection to the Rust service.

## Plan Manager

`macros/plan-manager.js` replaces Define Plan and Dispatch Run.

Plan Manager reads `.autoscribe/control-state.json`, which is written by
`svc refresh`. It presents all known plans ordered by a decaying frecency score
based on successful dispatch use. Editing a plan writes an atomic local draft to
`.autoscribe/plans/<plan-slug>.json`; the next `svc refresh` validates, stores and
uploads it.

`Copy Git Marker` copies two Git trailers:

    Autoscribe-Plan: plan.example
    Autoscribe-Plan-Title: Human Readable Hint

Only `Autoscribe-Plan` is machine-significant. Stage the intended target files
with Obsidian Git, use an ordinary human commit message, paste the marker, and
commit. An ordinary commit without the marker is ignored by AutoScribe.

## Git ownership

The editorial/master branch is user-owned. AutoScribe never creates automatic
master commits. Dispatch and response forensics are committed only to
`refs/heads/autoscribe/inflight`.

## Write Responses

Write Responses first saves the response candidate on the inflight ref. A target
is automatically writable only when master is clean and byte-identical to the
source that was dispatched. Dirty or clean-but-diverged targets are reported as
requiring a decision and are left untouched. A successful write is deliberately
left dirty for editorial review.

## Durable local state

`.autoscribe/` is operational state and should be excluded through
`.git/info/exclude`, not committed. The installer adds that exclusion.

Dashboard system state reads the current Git worktree directly and reads
pipeline/catalogue state from the most recent `.autoscribe/control-state.json`.
Run `svc refresh` from the vault root when you want AutoScribe to reconcile.
