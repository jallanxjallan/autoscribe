# obs feeder

Python feeder for scanning the active Obsidian vault and moving records to and
from the AutoScribe pipeline.

The repository mirrors the pipeline layout:

```text
~/AutoScribe/
  pipeline/src/asc/
  feeder/src/obs/
```

Install from the feeder project root:

```bash
cd ~/AutoScribe/feeder
pip install -e .
```

## Active vault and state

`obs` resolves the active vault from the current working directory's git root.
The vault contains Markdown content only. Generated JSON state is stored outside
the repository at:

```text
${AUTOSCRIBE_HOME:-${XDG_DATA_HOME:-~/.local/share}/autoscribe}/obsidian/vaults/<vault-name>-<root-hash>/
```

For example, running inside `~/Studio/Articles` uses:

```text
~/.local/share/autoscribe/obsidian/vaults/articles-<root-hash>/
```

The state tree is:

```text
selections/<operation>.json
workflow/plans/*.json
workflow/runs/current-run.json
writing/writeback-results.json
writing/writenew-results.json
```

Use `obs state` to print the active vault and resolved state directory.

## Commands

```bash
obs state
obs scan [--public]
obs upload-instructions [--dry-run] [--force]
obs upload-plans [--dry-run] [--force]
obs dispatch-run [--dry-run] [--manifest PATH]
obs writeback [--dry-run] [--limit N]
obs writenew [TARGET_DIR] [--dry-run] [--limit N]
```

`--vault PATH` remains available for explicit targeting, but normal operation is
pwd-driven.
