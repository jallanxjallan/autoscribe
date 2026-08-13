# Obsidian Adapter Contract

Obsidian is the first AutoScribe frontend. This directory records the boundary;
it intentionally contains no JavaScript implementation yet.

The adapter may:

- open a modal or dashboard panel;
- collect file, plan, and user-decision selections;
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
| Dispatch Run | file/plan validation then dispatch command | accepted notice and dispatch identity |
| Write Responses | pending-result query then write command | conflicts or committed wikilinks |
| File State | file-state query | Git, sync, dispatch, response state |
| File History | history query plus guarded restore command | versions, runs, writebacks, stash state |
| System Status | overview and reconciliation queries | pending, uncertain, failed, recovery choices |

The transport is deliberately undecided. A CLI/subprocess protocol is the
natural first choice for existing Obsidian macros. Unix sockets or another IPC
transport can be introduced later without altering commands, queries, or domain
state transitions.
