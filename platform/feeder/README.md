# obs feeder

Python service boundary between the Obsidian client and AutoScribe.

The client owns rendering, workspace behavior, result writeback, and
Obsidian-specific reference resolution. Feeder owns filesystem scans, Git state,
pipeline uploads, plan persistence, dispatch, and result retrieval.

Install:

```bash
cd ~/AutoScribe/feeder
pip install -e .
```

## Commands

```bash
obs state
obs scan [--public]
obs upload-instructions [--dry-run] [--force]
obs upload-instruction SOURCE --input RESOLVED.md [--metadata META.yaml]
obs dispatch-run [--dry-run] [--branch BRANCH]
obs retrieve-results [--dry-run] [--branch BRANCH]
```

Markdown instruction uploads and Markdown result writeback do not use Pandoc.
The feeder parses YAML frontmatter directly and sends or writes the Markdown
body unchanged. Pandoc is reserved for actual document-format conversion.

`retrieve-results` reads each waiting `autoscribe/run/*` flight branch, takes the
record identities from its dispatch manifest, and calls:

```bash
asc export extract-selected IDENTITY...
```

The retrieved result records are emitted as NDJSON on stdout. Feeder does not
write them into Markdown files; Obsidian owns that step.

Obsidian panels use the synchronous JSON IPC boundary:

```bash
printf '%s' '{"operation":"vault.state","vault":"/path/to/vault"}' \
  | obs --vault /path/to/vault ipc
```

Result retrieval is available over IPC as `results.retrieve`, with optional
`branch` and `dry_run` fields.

Retrieve Results archives full exporter records and returns normalized records. Use `--json` for NDJSON output.
