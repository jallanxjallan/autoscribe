# Current local contracts

| Command / state | Contract |
| --- | --- |
| `svc refresh` | Reconcile local plans/instructions, scan marked Git commits, dispatch exact commit contents, refresh durable Control state. |
| Git trailer | `Autoscribe-Plan: <slug>` triggers dispatch when encountered by refresh. |
| Human hint | `Autoscribe-Plan-Title: <text>` is ignored by the machine parser. |
| `.autoscribe/plans/*.json` | Local Plan Manager drafts ingested by refresh. |
| `.autoscribe/control-state.json` | Atomic read-only snapshot consumed by Obsidian Control. |
| `refs/heads/autoscribe/inflight` | Machine-owned immutable dispatch/response forensic history. |
| editorial/master branch | Human-owned; no automatic AutoScribe commits. |
| `write-responses` | Save response candidate to inflight, report master state, write only safe targets. |

The old interactive `dispatch-run` contract is retired. `__dispatch-run` is a
private implementation command invoked only inside a detached worktree by
`svc refresh`.
