# AutoScribe Rust service

`svc` is currently a command-line reconciler. There is no persistent local
service session or live Obsidian IPC requirement.

## Normal command

Run from a vault Git worktree:

    svc refresh

`svc refresh` also ensures `/.autoscribe/` is present in the repository-local `.git/info/exclude`, so Plan Manager drafts and Control state never appear in normal Git/Obsidian Git status.

One refresh pass:

1. builds the vault-wide slug index;
2. synchronizes changed local instructions without committing master;
3. ingests locally edited plans from `.autoscribe/plans/`;
4. scans new commits on the current branch for `Autoscribe-Plan:` trailers;
5. dispatches eligible slugged Markdown files changed by each marked commit,
   using a detached worktree at that exact commit;
6. records byte-precise source lineage on `refs/heads/autoscribe/inflight`;
7. increments the successfully used plan's decaying frecency score; and
8. atomically writes `.autoscribe/control-state.json` for Obsidian Control.

The dispatch cursor is stored in the service SQLite database. A commit without
an `Autoscribe-Plan:` trailer is ignored. The optional
`Autoscribe-Plan-Title:` trailer is a human hint only.

## Git boundary

AutoScribe makes no automatic commits on the editorial/master branch. Human
commits made through Obsidian Git or the normal Git CLI are authoritative.
Machine forensics live on `refs/heads/autoscribe/inflight`.

The private `__dispatch-run` command is an implementation detail used only by
`svc refresh` inside a detached worktree so the existing Pandoc/dispatch path
operates on the exact source commit. It is not an interactive dispatch API.

## Responses

The existing `write-responses` command remains the writeback boundary. Response
candidates are saved on the inflight ref before master is inspected. Clean,
unchanged targets may be written and are left dirty; dirty or committed-diverged
targets are left untouched and reported as decision-required.
