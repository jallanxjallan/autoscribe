# Control scripts

These scripts run inside Obsidian Desktop. They intentionally depend on the Obsidian app object, the local vault adapter, DOM APIs, and Node access supplied by the desktop application.

Visible workflow files own their configuration, display code, and orchestration:

- `macros/` contains complete QuickAdd macros.
- `queries/` contains complete DataviewJS queries.
- `System Status.md` contains the detailed DataviewJS diagnostics view.

`scripts/lib/` contains reusable mechanics shared by more than one visible workflow. Other `scripts/` subdirectories contain non-display domain and persistence support used by visible workflows. There are no cross-client adapters or shadow renderer files for panels or queries.
