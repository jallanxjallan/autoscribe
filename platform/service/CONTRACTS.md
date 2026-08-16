# Active frontend contracts

Rust owns state and policy. A frontend may select an operation, send identifiers
or user-entered values, and render the response. It must not run Git, inspect
SQLite, infer writeback state, construct dispatch payloads, or rewrite sources.

| Command | Input | Output and policy |
| --- | --- | --- |
| `dispatch-run` | `{version, plan, documents[]}` | JSON receipt. Rust resolves slugs, converts with Pandoc, records lineage, uploads, and enqueues. |
| `write-responses` | `{version}` | NDJSON manifest. Rust checkpoints a dirty target, overwrites it, sets review metadata, commits it, and acknowledges the response. |
| `system-snapshot` | `{version}` | JSON Git summary and pipeline counts. |
| `git-files` | `{version, action, ...}` | JSON inspect/commit/history/stash/restore result. Repository is the process working directory. |
| `define-plan-snapshot` | `{version}` | JSON server and locally authored catalog snapshot. |
| `plan-save` | plan record and instructions | JSON save/upload receipt. |
| `instructions-sync` | root and selected relative paths | JSON comparison/upload receipt. |

## Writeback invariants

- Source identity must match the current target's top-level slug.
- A dirty target is committed alone first with purpose `writeback-checkpoint`.
- Current frontmatter is preserved; top-level `status` and `producer` become
  `needs-review` and `ai`.
- The response body is committed alone with purpose `dispatch-writeback`.
- Unrelated staged or working-tree changes are never included.
- NDJSON reports the optional checkpoint commit, writeback commit, path,
  identities, outcome, and resulting properties.
- Git/SQLite/export partial completion is resumable.

## Dispatch invariants

- The frontend supplies no paths and no contents.
- File resolution inspects only top-level `slug`.
- Missing and duplicate slugs are hard errors.
- The plan slug must exist in the reconciled catalog.
- Pandoc output must identify the requested slug.
- A source with an unexported response cannot be dispatched again.
- The inflight ledger does not alter HEAD, the index, or the working tree.

## Git boundary

Only Rust executes Git. Obsidian calls service commands and displays results.
Build products live outside the source tree at
`~/.cache/autoscribe/cargo/service` by default.
