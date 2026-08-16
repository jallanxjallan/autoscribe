# AutoScribe Obsidian Control

This package supports Obsidian Desktop only. It assumes:

- `_control` resolves to this directory from the active vault;
- QuickAdd runs the files in `macros/`;
- DataviewJS runs `Dashboard.md`, `System Status.md`, and `queries/`;
- the vault adapter exposes a local filesystem path; and
- Node modules and local command-line tools are available inside Obsidian Desktop.

Rust owns every Git operation. Dispatch Run sends only plan/document slugs;
Write Responses renders the service's NDJSON outcome manifest. If a writeback
target is dirty, the service checkpoints it before replacing and committing it.
Obsidian does not inspect or invoke Git directly.

There is no cross-client runtime, browser-only storage path, or alternative UI adapter in this package. A future client should use its own frontend package and call the service boundary independently.

## Layout

- `macros/`: QuickAdd entry points and self-contained Obsidian workflows.
- `queries/`: DataviewJS query notes.
- `System Status.md`: detailed project diagnostics opened from the Dashboard.
- `scripts/ui/`: larger Obsidian modal implementations used by QuickAdd launchers.
- `scripts/lib/`: reusable Obsidian and local-filesystem mechanics.
- `scripts/plans/` and `scripts/selections/`: active plan and selection support.
- `templates/` and `templater/`: vault note templates and Templater helpers.

Restart Obsidian or reload QuickAdd/Dataview after replacing `_control`, because Node may retain previously loaded modules for the life of the Obsidian process.

Service builds default to `~/.cache/autoscribe/cargo/service`. Override source
discovery with `AUTOSCRIBE_ROOT`, the target with
`AUTOSCRIBE_CARGO_TARGET_DIR`, or the executable with `SVC_BIN`.
