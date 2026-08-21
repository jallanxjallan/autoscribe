# Control configuration

The YAML files in this directory are Control's editable definition layer.
JavaScript owns behaviour. Vocabularies, mappings, paths, option sets, limits,
ordering, protocol names, defaults, maintenance lists and similar declarative
values belong here.

The intention is practical: once the refactor is installed, you should be able
to refine the system by editing these files rather than hunting definitions
through JavaScript.

## Editing model

Normal config edits are re-read when a file's mtime or size changes. The next
macro/query operation should therefore see the new value without an Obsidian
restart. Replacing JavaScript itself is different: after installing a new code
tree, reload Obsidian so QuickAdd/Dataview do not retain an old module instance.

Run this after editing config:

    /home/jeremy/Work/Loom/platform/client/obsidian/control/scripts/config-check.js

Warnings are intentional. They identify accumulated values that do not fit the
currently declared vocabulary; they do **not** prevent Control from running.
Errors mean a config reference is structurally broken and should be fixed before
using the affected operation.

## Files

- `vocabulary.yaml` — controlled frontmatter terms (`stage`, `status`, `action`, etc.).
- `records.yaml` — Set Note Type groups, labels, optional pipeline/instruction slug prefixes, template paths and per-choice defaults; templates own document shape/frontmatter fields. Omit `prefix` for ordinary notes that should remain undiscoverable by slug.
- `instructions.yaml` — plan instruction scopes and resolver mapping; Markdown templates/files define instruction records.
- `annotations.yaml` — annotation keys, types, ordering and annotation display limits.
- `paths.yaml` — machine paths, vault mount names, runtime dirs and command names.
- `workflow.yaml` — workflow modes, operational defaults, limits and writeback defaults.
- `protocol.yaml` — service operation names, versions, namespaces and contract keys.
- `ui.yaml` — query fields, sort modes, columns and missing-value display.
- `dashboard.yaml` — dashboard actions, links and resource folders.
- `queries.yaml` — Dataview/query schema, properties, ordering and labels.
- `service.yaml` — Rust service discovery/build paths, environment names and defaults.
- `maintenance.yaml` — paths that are obsolete and should be removed from Control.

## YAML subset used by Control

`scripts/lib/config-loader.js` intentionally supports a small, predictable YAML
subset rather than depending on an Obsidian-side YAML package. Use the forms in
these files:

- two-space indentation;
- nested mappings;
- lists of scalar values;
- comments beginning with `#`;
- quoted or unquoted scalar strings;
- numbers, booleans and `null`;
- JSON-style inline `[]` and `{}` when an empty list/map is needed.

Do not use tabs, YAML anchors, block scalars (`|` / `>`), or lists of mapping
objects. Use a named mapping instead of a list of objects; this also makes the
config easier to edit by hand. Duplicate keys are rejected by the loader.

## Things deliberately left for manual resolution

This extraction preserves existing behaviour rather than silently normalising
old values. `scripts/config-check.js` will therefore warn about legacy values
such as `draft`, `research`, `empty`, `active`, `imported`, `open`, and
`needs-review` where they sit outside the newly declared stage/status
vocabulary. That is the point: the conflicts are visible here for you to decide.

`paths.yaml` likewise preserves the Instructions vault path found in the source tree
at refactor time. It is labelled there because the Control root has moved to
Loom but the correct new Instructions location was not specified during this pass.

## Bootstrap exception

Every Obsidian macro has to find *something* before it can load config. The
existing `_control` vault mount is therefore the bootstrap convention used by
entry-point macros. `paths.control_mount` documents the intended mount name and
is used once Control is loaded, but changing the mount itself is a two-step
operation: change/recreate the vault symlink and then update the config/code
bootstrap together. This is the one definition that cannot bootstrap itself.

If a new declarative value appears in JavaScript, treat that as a maintenance
smell: move it into the appropriate config file and have the code consume it.
