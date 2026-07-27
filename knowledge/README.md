# _control

`_control` is the shared control and inspection layer for Studio vaults.

It is paired with `../core/`:

- `core/` is copied into each vault as the local Obsidian runtime skeleton
- `control/` is symlinked into each vault as `_control`

It contains:

- templates
- Dataview queries
- DataviewJS scripts
- create-only and selection-only macros
- workflow documentation
- configuration notes

No project content should ever live here.

## Template Ownership

- The canonical authored note templates live directly in this `templates/` directory.
- `templates/` contains only active authored note classes.
- Each active template contains its own create-time runtime hook.
- Shared JS in `scripts/create_note_runtime.js` remains the single slug-initialization path and emits the generic created-note confirmation.
- Vault macros resolve `_control/templates/...` and must not rely on retired template aliases or compatibility shims.

## Directory Map

- `queries/`: inspection queries for authored notes.
- `scripts/`: shared DataviewJS query logic.
- `templates/`: reusable note templates exposed to Studio vaults.
- `macros/`: create-only and selection-only command palette or QuickAdd actions.
- `docs/`: shared editorial and metadata conventions.
- `config/`: stable settings references.

## Rules

- Keep `_control` deterministic and reusable across Studio vaults.
- Do not store project notes, scratch notes, pipeline output, or experiments here.
- Keep the active `_control/` surface aligned with the live ontology only.
- If legacy material must be retained, store it outside this tree instead of under `_control/`.
