# obs feeder

Python service boundary between the Obsidian client and AutoScribe.

The client owns rendering, workspace behavior, and Obsidian-specific reference
resolution. Feeder owns filesystem scans, Git state and commits, Pandoc calls,
pipeline uploads, pipeline plan persistence, dispatch, and writeback.

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
obs dispatch-run [--dry-run] [--manifest PATH]
obs writeback [--dry-run] [--limit N]
obs writenew [TARGET_DIR] [--dry-run] [--limit N]
```

Obsidian panels use the synchronous JSON IPC boundary:

```bash
printf '%s' '{"operation":"vault.state","vault":"/path/to/vault"}' \
  | obs --vault /path/to/vault ipc
```

Plans have no client-side manifest. `plans.list`, `plan.load`, and `plan.save`
operate through the pipeline. Instruction catalog calls merge pipeline records
with active-vault and configured Library-vault Markdown files.
