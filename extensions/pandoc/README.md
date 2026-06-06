# Import Vault Pandoc Filter Kit

These filters are meant for importing old `.docx` / `.odt` material into a provisional Obsidian-style vault.

The assumed slug shape is:

```text
prv.<kebab-case-input-file-stem>.<timestamp>
```

Example:

```text
prv.warehouse-delay-notes.20260504143217
```

## Files

### `inject_provisional_slug.lua`

Adds `slug:` metadata if the document does not already have one.

### `import_source_meta.lua`

Adds provenance metadata under `source:`:

```yaml
source:
  imported_at: ...
  original_path: ...
  original_filename: ...
  original_stem: ...
  original_format: ...
  import_method: pandoc-import-vault
```

If a non-map `source` field already exists, it writes to `import_source:` instead of clobbering it.

### `normalize_legacy_styles.lua`

Works best with:

```yaml
from: docx+styles
```

It maps common Word styles into cleaner Pandoc structures:

- boxout/sidebar/case-study styles -> fenced div class `.boxout`
- caption styles -> fenced div class `.caption`
- verse/poem styles -> fenced div class `.verse`
- source/reference styles -> fenced div class `.source`
- pull quote styles -> blockquote
- selected character styles -> emphasis, strong, small caps, superscript, subscript

### `strip_word_junk.lua`

Removes conservative Word residue:

- empty spans/divs/paragraphs/headings
- page-break and section-break raw blocks/inlines
- obvious generated table-of-contents residue

### `normalize_whitespace.lua`

Normalizes whitespace in prose:

- non-breaking spaces -> normal spaces
- tabs -> spaces
- soft line breaks -> spaces
- repeated inline spaces -> single spaces
- trims leading/trailing inline spaces

### `normalize_headings.lua`

Repairs common legacy heading issues:

- removes empty headings
- promotes leading Word `Title` and `Subtitle` styles into metadata
- promotes heading depth if the document starts at H2/H3 instead of H1
- converts short bold-only paragraphs into H2 headings

This one is useful but more opinionated than the others. If it over-promotes legacy bold paragraphs, remove it from the chain.

### `track_changes_to_notes.lua`

Use only with:

```yaml
track-changes: all
```

It converts deletion spans to strikeout, preserves insertion spans, and turns Word comment spans into inline footnotes when Pandoc exposes comment metadata/text.

For ordinary import, prefer `track-changes: accept` and omit this filter.

## Suggested clean import chain

```yaml
from: docx+styles
to: markdown+yaml_metadata_block+pipe_tables+fenced_divs+bracketed_spans+strikeout
standalone: true
track-changes: accept
extract-media: assets/imported-media

filters:
  - inject_provisional_slug.lua
  - import_source_meta.lua
  - normalize_legacy_styles.lua
  - strip_word_junk.lua
  - normalize_whitespace.lua
  - normalize_headings.lua
```

## Suggested review-preserving chain

```yaml
from: docx+styles
to: markdown+yaml_metadata_block+pipe_tables+fenced_divs+bracketed_spans+footnotes+strikeout
standalone: true
track-changes: all
extract-media: assets/imported-media

filters:
  - inject_provisional_slug.lua
  - import_source_meta.lua
  - track_changes_to_notes.lua
  - normalize_legacy_styles.lua
  - strip_word_junk.lua
  - normalize_whitespace.lua
  - normalize_headings.lua
```

## Installation shape

Copy the Lua files into your Pandoc data-dir filters folder, for example:

```text
~/Workspace/Tools/pandoc/filters/
```

Copy the defaults files into the defaults location your Pandoc setup already uses.

Then your import function can keep calling:

```zsh
pandoc -d import_vault.yaml "$src" -o "$dest"
```

## Notes

- These filters are intentionally standalone. There is no shared Lua helper module, so each file can be tested independently.
- `normalize_headings.lua` is the most opinionated filter. Try the chain with and without it.
- `extract-media` is included in the sample defaults, but you may want to change the target folder before importing a large archive.
