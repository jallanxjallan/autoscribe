# Filters

Pandoc Lua filters are organized by function rather than by workflow.

Workflows are assembled through Pandoc defaults files, which select and order
reusable filters for a given pipeline. Keep filters independent, composable,
and narrow: source import cleanup belongs under `import/`, metadata shaping
under `metadata/` or `identity/`, and final record emission under `emit/`.

## Import preamble cleanup

For source documents that may contain publication/editorial preamble material,
use the filters as separate jobs in this order:

```yaml
lua-filter:
  - filters/import/drop_source_frontmatter.lua
  - filters/import/drop_instruction_preamble.lua
  - filters/import/drop_leading_separators.lua
```

`drop_source_frontmatter.lua` clears source metadata before NDJSON emission using
an explicit AutoScribe namespace policy. Pandoc merges source frontmatter,
defaults-file metadata, metadata-file values, and command-line metadata before
Lua filters run, so the filter cannot detect origin after the fact. It keeps
only metadata passed under the reserved AutoScribe namespace and unwraps it for
later filters and emitters.

Command-line form:

```bash
--metadata=asc_type:prompt \
--metadata=asc_slug:prv.example.001 \
--metadata=asc_job_slug:job.normalize-import.001
```

Defaults/metadata-file form:

```yaml
metadata:
  asc:
    type: prompt
    slug: prv.example.001
    job_slug: job.normalize-import.001
```

Both forms become ordinary metadata keys after the filter runs:

```yaml
type: prompt
slug: prv.example.001
job_slug: job.normalize-import.001
```

Run source/provenance injection filters after `drop_source_frontmatter.lua` if
those details should be deliberately emitted. Use `asc_*` or `asc:` only for
metadata that should survive source cleanup.

## Current organization

```text
_lib/          shared helpers and old diagnostic helpers
content/       content-shape conversions
import/        client-side import hygiene, source cleanup, sentinels
identity/      slug/kind/identity normalization
metadata/      metadata extraction or shaping
emit/          final output/NDJSON/clipboard/path emitters
formatting/    output-format presentation filters
media/         image/media handling
select/        filtering/selective inclusion
transform/     structural and body transformations
```
