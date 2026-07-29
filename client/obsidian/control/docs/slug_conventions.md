# Slug Conventions

## Format

- `<prefix>.<project>.<hint>.<identity>`
- lowercase ASCII only
- `prefix` comes from the template `slug:` field
- `project` comes from the vault-local `_vault_registry.json` mnemonic
- `hint` is kebab-case derived from the filename
- `identity` is exactly 8 lowercase alphabetic characters

## Rules

- Build the full slug inside Obsidian with local JavaScript only.
- Keep slugs stable after publication or pipeline use.
- Avoid duplicate slugs within the same vault.
- Treat the full slug as opaque in downstream tooling.
- Reserve numeric suffixes for chunk ids only.

## Examples

- `psg.hhp.chapter-03-opening.kmzqtxra`
- `ins.hhp.submission-rules.abcdwxyz`
- `pkg.hhp.story-pipeline.qrstuvwx`
