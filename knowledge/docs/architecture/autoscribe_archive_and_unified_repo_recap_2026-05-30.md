# AutoScribe chat recap — archive and unified repo migration

Date: 2026-05-30

## Core decision

The AutoScribe architecture now feels settled enough to stop continuing the current prototype as-is and begin a controlled archive-and-rebuild process.

The agreed direction is:

- Archive everything developed to date.
- Preserve the existing repos as historical evidence and working prototypes.
- Start over in a new unified repo.
- Build the new repo around the settled architecture rather than dragging the old repo structure forward.

The new repo should eventually include:

- the server-side pipeline
- client/interface code
- extension scripts and filters
- future RAG/engine components
- the knowledge base as an Obsidian vault
- fixtures, tests, and architecture notes

The main principle is: this should be a clean reconstruction from the architecture, not a refactor-in-place.

## Recommended archive approach

Before creating the new repo, each existing repo/package should receive a final custody commit and tag.

Suggested commit message:

```text
SNAPSHOT: archive pre-consolidation AutoScribe prototype

Freeze the current multi-repo prototype before rebuilding AutoScribe as a
single integrated repo containing the pipeline, client/interface layer,
extension scripts and filters, and the knowledge base vault.

This snapshot preserves the exploratory implementation history before the
new architecture is reconstructed around the settled atomic step pipeline,
client-owned document preparation, external extension components, and
Obsidian-backed knowledge/control material.
```

Suggested tag:

```bash
git tag archive/pre-consolidation-2026-05-30
```

or:

```bash
git tag pre-unified-repo
```

After tagging, the old repos should be left alone except for emergency reference.

## New repo shape

A clean top-level shape was proposed:

```text
autoscribe/
├── README.md
├── pyproject.toml
├── package.json
├── .gitignore
├── docs/
│   ├── architecture/
│   ├── decisions/
│   ├── operations/
│   └── glossary.md
├── pipeline/
│   └── src/asc/
├── client/
│   ├── obsidian/
│   ├── electron/
│   └── cli/
├── extensions/
│   ├── engines/
│   ├── scripts/
│   ├── filters/
│   └── rag/
├── knowledge/
│   └── vault/
├── tests/
│   ├── fixtures/
│   ├── pipeline/
│   ├── client/
│   └── extensions/
├── samples/
│   ├── documents/
│   ├── jobs/
│   └── ndjson/
└── tools/
    ├── dev/
    ├── maintenance/
    └── migration/
```

Conceptual lanes:

```text
pipeline/    server-side execution, Redis, ledger, workers, models
client/      Obsidian/Electron/CLI interfaces and local document prep
extensions/  importable engines, scripts, Lua filters, RAG components
knowledge/   Obsidian vault: instructions, docs, decisions, examples
docs/        architectural record and human-readable operating doctrine
tests/       fixtures, smoke tests, regression cases
```

## Migration rule

The key migration question should be asked before copying any code:

> Does this component belong to the settled architecture, or was it scaffolding used to discover the architecture?

Likely keep or rebuild:

```text
NDJSON stream handling
Pydantic model validation
Redis key helpers
atomic step runtime model
control upload records
driver/instruction models
extension import mechanism
Pandoc/Lua filters that own document parsing/chunking
Obsidian vault selection/query ideas
ledger step table design
status derived from ledger + Redis
```

Likely avoid carrying forward directly:

```text
old loop-based worker assumptions
old stage/upload public API
legacy profile terminology
reverse ULID→slug normal pipeline lookup
bulk template assignment flows
stale query-state-dependent writeback
server-side job ownership
client/server responsibilities blurred together
compatibility shims
```

## Architecture docs to create first

Before copying code, the new repo should start with short architecture documents:

```text
docs/architecture/system-boundaries.md
docs/architecture/atomic-step-pipeline.md
docs/architecture/client-document-prep.md
docs/architecture/control-records.md
docs/architecture/extensions.md
docs/architecture/ledger.md
docs/decisions/0001-new-unified-repo.md
docs/glossary.md
```

Suggested first ADR:

```markdown
# ADR 0001: Rebuild AutoScribe as a unified repo

AutoScribe has reached an architectural breakpoint. The exploratory
multi-repo prototype will be archived, and the production-oriented system
will be reconstructed in a new unified repository.

The new repository will contain:

- the server-side pipeline
- client/interface code
- extension scripts, engines, filters, and future RAG components
- an Obsidian knowledge/control vault
- fixtures and regression tests

The old repositories remain historical evidence and reference material.
They are not treated as source structure for the new implementation.
```

## Suggested initial repo commands

```bash
mkdir -p ~/Workspace/autoscribe-new
cd ~/Workspace/autoscribe-new
git init
```

Create skeleton:

```bash
mkdir -p   docs/architecture   docs/decisions   docs/operations   pipeline/src/asc   client/obsidian   client/electron   client/cli   extensions/engines   extensions/scripts   extensions/filters   extensions/rag   knowledge/vault   tests/fixtures   tests/pipeline   tests/client   tests/extensions   samples/documents   samples/jobs   samples/ndjson   tools/dev   tools/maintenance   tools/migration
```

Initial commit:

```bash
git add .
git commit --allow-empty -m "SNAPSHOT: initialize unified AutoScribe repo"
```

First real commit after skeleton:

```text
FACT: document settled AutoScribe architecture
```

## Preferred migration order

The proposed migration order is:

1. `docs/` architecture and glossary
2. `knowledge/vault/` with durable instructions, decisions, and examples
3. core Pydantic models
4. Redis key/state helpers
5. NDJSON stream dispatch
6. control records and slugmap
7. atomic enqueue/worker path
8. ledger/status/export
9. Pandoc/Lua filters
10. Obsidian/client interface
11. extension packages
12. smoke tests and fixtures

This sequence builds from concept to model to execution to interface, instead of reproducing the order in which the prototype evolved.

## User’s immediate next step

The user plans to run a few tests to filter and collate saved architecture notes from prior chats.

If the test runs work, the user will then begin the migration.

The recommended collation pipeline is:

```text
chat archives
→ extract architecture notes
→ collate by topic
→ remove duplicates / obsolete decisions
→ keep only current doctrine
→ save into knowledge vault
```

Suggested topic buckets:

```text
architecture/
  atomic-step-pipeline.md
  client-server-boundaries.md
  redis-key-schema.md
  ledger-and-export.md
  controls-drivers-instructions.md
  extensions-and-scripts.md
  pandoc-and-chunking.md
  obsidian-client-workflow.md
  product-positioning.md
  glossary.md
```

## Important warning: stale doctrine contamination

The main risk in collating architecture notes is accidentally carrying obsolete decisions into the new repo.

Recommended status labels for notes:

```text
status: current
status: superseded
status: historical
status: unresolved
```

Only `status: current` and possibly `status: unresolved` should feed the new repo’s core architecture docs. Superseded and historical material can live in an archive folder inside the knowledge vault.

## Useful reference from the uploaded May 16 recap

The May 16 recap is a good model for source notes worth preserving. It captured both implementation-level decisions and larger doctrine.

Key May 16 themes included:

- stripping away compatibility layers
- removing fallback machinery
- avoiding speculative abstractions
- simplifying engine and worker contracts
- preserving raw records
- validating only the small execution contract
- failing clearly when dependencies are wrong
- keeping the pipeline atomic and resumable
- preferring obvious files and functions over abstract registries

That recap’s key doctrine was:

> AutoScribe should not be trying to anticipate every producer shape or engine behavior. It should preserve raw input, validate the small execution contract, run the requested step, and either produce a canonical result or fail clearly.

## Suggested commit after architecture-note collation

```text
FACT: collate settled AutoScribe architecture notes

Extract and organize current architecture decisions from prior development
chats before starting the unified repository migration. Separate durable
doctrine from superseded prototype decisions so the new repo can be built
from the settled design rather than inherited implementation history.
```

## Standing caution

This migration risks orphaning or overwriting manual work if it becomes too automated.

The user’s own rule applies:

> The user remains responsible for any pipeline action that overwrites manual work.

Scripts may help inventory, copy, diff, and test, but inclusion decisions should remain deliberate.

## Bottom line

This is the right point for a controlled freeze and restart.

The old system should become the archive. The new repo should become the product-shaped implementation of the settled architecture.
