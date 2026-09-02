# Obsidian Adapter Contract

Obsidian is the first AutoScribe frontend. This directory records the boundary;
the implementation lives in the separate control package.

The adapter may:

- open a modal or dashboard panel;
- collect file and plan selections;
- invoke one Rust service command or query;
- display typed views, notices, warnings, links, and errors;
- launch long-running service work without keeping a modal open.

The adapter must not:

- read or write the service SQLite database;
- invoke Git, Redis, or the pipeline directly;
- build, normalize, hash, or persist a dispatch payload;
- generate a dispatch identity;
- decide whether a dispatch succeeded;
- reconstruct a payload for retry;
- infer file/run state from tags or filenames;
- synchronize the service store itself;
- hide a state transition inside an event handler.

## Initial Obsidian operations

| Obsidian surface | Service interaction | Rendered output |
| --- | --- | --- |
| Library State | catalog and instruction queries; upload command | local/server state and notices |
| Define Plan | plan list/get/save and catalog queries | titles, validation, saved identity |
| Dispatch Run | plan slug and document-slug manifest | dispatch receipt |
| Write Responses | one automatic write command | NDJSON checkpoint/writeback outcome manifest |
| File State | file-state query | Git, sync, dispatch, response state |
| File History | history query plus guarded restore command | versions, runs, writebacks, stash state |
| System Status | overview and reconciliation queries | pending, uncertain, failed, recovery choices |

The adapter invokes the `svc` subprocess in the vault working directory. Cargo
output is resolved outside the source tree. This transport does not move Git or
writeback policy into JavaScript.
