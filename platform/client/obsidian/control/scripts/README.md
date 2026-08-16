# Control scripts

Visible workflow files own their configuration, display code, and orchestration:

- `macros/` contains complete QuickAdd macros.
- `queries/` contains complete DataviewJS queries.
- `System Status.md` contains the detailed DataviewJS status surface.

`scripts/lib/` contains reusable mechanics shared by more than one visible workflow. Other `scripts/` subdirectories contain non-display domain and persistence support used by visible workflows. Git and writeback policy belong exclusively to the Rust service.
