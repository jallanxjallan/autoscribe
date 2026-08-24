# AutoScribe Obsidian Control

This package supports Obsidian Desktop only. It assumes:

- `_control` resolves to this directory from the active vault;
- QuickAdd runs the files in `macros/`;
- DataviewJS runs `Dashboard.md`, `System Status.md`, and `queries/`;
- the vault adapter exposes a local filesystem path; and
- Node modules and local command-line tools are available inside Obsidian Desktop.

Rust owns every Git operation. Dispatch Run only resolves the selected Markdown files to their document slugs and sends those slugs with the selected plan; it does not flatten links, expand transclusions, or rewrite document content.
Write Responses renders the service's NDJSON outcome manifest. If a writeback
target is dirty, the service checkpoints it before replacing and committing it.
Obsidian does not inspect or invoke Git directly.

There is no cross-client runtime, browser-only storage path, or alternative UI adapter in this package. A future client should use its own frontend package and call the service boundary independently.

## Layout

- `macros/`: thin QuickAdd entry points.
- `queries/`, `Dashboard.md`, `System Status.md`, `templater/`, and `scripts/queries/`: Obsidian runtime entry points. Their first Control import must bootstrap `scripts/lib/control-loader.js`; relative Control imports and secondary dynamic loaders are forbidden.
- `System Status.md`: detailed project diagnostics opened from the Dashboard.
- `scripts/lib/`: reusable Obsidian and local-filesystem mechanics.
- `scripts/plans/` and `scripts/selections/`: active plan and selection support.
- `templates/` and `templater/`: vault note templates and Templater helpers.

Control entry points clear the cached physical Control module tree at invocation, so edited or moved modules do not survive in Electron's long-running Node cache. Dashboard actions re-enter through a fresh loader as well. A full Obsidian restart should not normally be required after replacing `_control`. Direct Electron API access is confined to explicit platform adapters under `scripts/lib/`; the Dashboard clipboard poll uses that adapter because synchronous polling is not equivalent to the permission-gated browser clipboard API.

Service builds default to `~/.cache/autoscribe/cargo/service`. Override source
discovery with `AUTOSCRIBE_ROOT`, the target with
`AUTOSCRIBE_CARGO_TARGET_DIR`, or the executable with `SVC_BIN`.
