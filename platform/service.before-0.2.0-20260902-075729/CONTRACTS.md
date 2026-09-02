# Current local contracts

| Command / state | Contract |
| --- | --- |
| `svc refresh` | Reconcile local plans/instructions and refresh durable Control state. It does not dispatch editorial commits. |
| `svc watch-dispatch` | Foreground watcher that consumes marked commits in branch order and retries the first failed commit without advancing its cursor. |
| Plan trailer | Exactly one `Autoscribe-Plan: <slug>` selects the plan. |
| Document trailer | One or more `Autoscribe-Document: <document slug>` entries select records; their paths are resolved inside the exact commit snapshot. |
| Human hint | `Autoscribe-Plan-Title: <text>` is ignored by the machine parser. |
| `.autoscribe/plans/*.json` | Local Plan Manager drafts ingested by refresh. |
| `.autoscribe/control-state.json` | Atomic read-only snapshot consumed by Obsidian Control. |
| `refs/heads/autoscribe/inflight` | Machine-owned immutable dispatch/response forensic history. |
| editorial/master branch | Human-owned; no automatic AutoScribe commits. |
| `write-responses` | Save response candidate to inflight, report master state, write only safe targets. |

The old interactive `dispatch-run` contract is retired. `__dispatch-run` is a
private implementation command invoked only by `watch-dispatch` inside a
detached exact-commit worktree. The inflight snapshot is recorded before
Pandoc, upload, or enqueue begins.
