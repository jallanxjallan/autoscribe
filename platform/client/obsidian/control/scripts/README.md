# Control scripts

Visible workflow files own their configuration, display code, and orchestration:

- `macros/` contains complete QuickAdd macros.
- `queries/` contains complete DataviewJS queries.
- `panels/` contains complete DataviewJS panels.

`scripts/lib/` contains reusable mechanics shared by more than one visible workflow. Other `scripts/` subdirectories contain non-display domain and persistence support used by visible workflows. There are no shadow renderer files for panels or queries.
