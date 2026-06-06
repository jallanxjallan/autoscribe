# Vault Conventions

## Purpose

`_control` is the reusable control and inspection layer shared across Studio vaults.

## Allowed Contents

- templates
- inspection queries
- create-only and selection-only macros
- workflow conventions
- configuration notes

## Disallowed Contents

- project notes
- scratch notes
- pipeline output
- experiments
- temporary work products

## Related Vault Files

- authored notes may live anywhere outside `_control/`
- `_vault_registry.json` is a vault-local config file and may store the mnemonic used by Obsidian slug construction

## Note Creation

Active note creation is template-driven.
Each active template runs its own embedded create macro hook, and shared JS finalizes the slug plus the generic created-note confirmation.

## Archive Rule

If an item is no longer part of the stable shared layer and must be retained, move it outside the active `_control/` tree.
