# Canonical Control identity and enqueue revisions

Control is read directly from immutable Git objects through `asc/control/git.py`.
`accept_revision()` resolves the configured branch once and validates every
instruction, plan, reference, and capability declaration before returning a
snapshot. Invalid revisions fail, including when the invalid plan is not selected.
No checkout, archive, temporary extraction, Redis refresh, normalization, or
fallback to an earlier revision is performed.

`LoadedPlan.revision` is explicitly forwarded by enqueue to runtime construction
and instruction materialization. Instruction reads require a full immutable
commit ID and never resolve the branch. Each read validates that exact snapshot;
there is no persistent acceptance cache or working-tree dependency.

## Canonical source contract

Instructions remain Markdown under the existing `instructions/` and `context/`
paths. Their frontmatter contains exactly these fields:

```yaml
---
identity: spc_3N6K8R2V7M4Q9D1X
title: Line edit
description: Preserve the author's meaning.
---
Edit the supplied prose.
```

`identity` is client-supplied, unique across both directories, and matches
`(rol|ctx|spc)_[0-9A-HJKMNP-TV-Z]{16}`. The prefixes mean role, context, and task.
Identity changes represent replacement with a different instruction; ordinary
edits retain the identity. No identity is generated, inferred, or migrated by the
pipeline. Filenames and titles do not participate in identity resolution.
Duplicate YAML/JSON fields, aliases, absent fields, empty bodies and symlinks fail.
Bodies are retained without stripping whitespace.

Plans remain JSON under `plans/`, with this single representation:

```json
{
  "slug": "line-edit",
  "title": "Line edit",
  "description": "Edit prose",
  "steps": {
    "1": {
      "engine": "chatgpt",
      "engine_kind": "llm",
      "model": "cheap",
      "instructions": {
        "role": [],
        "context": [],
        "task": ["spc_3N6K8R2V7M4Q9D1X"]
      },
      "args": {}
    }
  },
  "capabilities": {
    "engines": {
      "chatgpt": {
        "kind": "llm",
        "step_fields": ["model", "temperature", "max_output_tokens"],
        "args_schema": {"type": "object", "additionalProperties": false}
      }
    },
    "models": {
      "cheap": {
        "engine": "chatgpt",
        "args_schema": {"type": "object", "additionalProperties": false}
      }
    },
    "local_scripts": {},
    "rag_profiles": {}
  }
}
```

An optional plan `scope` supports catalog filtering. Step keys must be contiguous
positive ordinals beginning at `1`; steps must be an object, not a list or JSON
string. Every step explicitly supplies `engine`, `engine_kind`, `instructions`
(with all three scope arrays), and `args`. Runtime parameters use their canonical
step fields, not aliases inside `args`. `model`, `script`, or `rag_profile` is
required according to engine kind. Step `label` is optional display text.

Capability metadata is embedded in each plan so its Git version is pinned
without introducing a new Control directory. The compiler must supply all four
registries. Every capability requires an object `args_schema` (JSON Schema
2020-12); both engine and selected capability schemas validate `args` without
coercion or inserting defaults. Only local schema references are allowed.
Engine `step_fields` declares allowed runtime parameters. Model metadata names
its owning engine. Conflicting declarations across plans reject the revision.
`control snapshot` schema version 4 exports the accepted commit's metadata;
`components` continues to describe installed extensions for authoring purposes.
Executable extension code remains in the configured Extensions installation;
this change pins capability metadata, not executable binaries.

Existing legacy Control publications must be republished in this canonical
format by the client before enqueue can accept them. This work does not edit
Control authoring files or Obsidian/client machinery.

## Materializations and identities

- Source documents and plans keep their existing human-readable slugs.
- Instructions have permanent opaque Control identities.
- Git commits select snapshots; Git blob IDs fingerprint exact instruction files.
- Server-generated ULIDs identify Redis instruction materializations.

`state:instruction_materializations:index` is a preferred-materialization cache
keyed by permanent instruction identity. Reuse requires a loadable record of the
correct kind, matching Control identity and blob fingerprint, and the configured
minimum remaining TTL. ULID timestamps and filesystem timestamps are never used.
A changed blob, expired/missing record, mismatched identity, or low TTL creates a
new ULID record with the configured instruction TTL. Existing records and their
TTLs are not modified. Concurrent enqueues may create independent valid versions;
the pointer is a hint, so no CAS protocol is needed for correctness. Old calls
continue using their recorded keys until those keys expire naturally.

## Removed and retained code

Removed `control_checkout`, archive/extraction imports, plan content/identity
aliases, server-generated plan identities, legacy instruction reference parsing,
engine inference/default repair, and instruction usage of the slugmap.
Removed obsolete modules:

- `asc/models/control/step.py`
- `asc/streams/control/list.py`
- `asc/streams/control/snapshot.py`

The shared `asc/state/slugmap.py` remains for source document and call slugs only.
This preserves ingest, source matching, reconciliation, and writeback identity.

One narrowly scoped durable-data adapter remains in `Instruction.load_redis`:
it discards old `slug`, `source_modified_ns`, and `source_size` fields while
loading already-materialized Redis records. This allows in-flight calls from
before deployment to finish. It does not accept legacy Control input or resolve
slugs, and those records cannot be reused because they lack source fingerprints.
The persisted Runtime reader still accepts its prior field aliases and scalar
instruction keys to drain existing records and handle call directives; canonical
Control validation rejects those authoring shapes before enqueue. Report-only
Git-reference properties in `LoadedPlan` remain to preserve the NDJSON contract.

## Change inventory

Modified `pyproject.toml` (JSON Schema dependency), this document,
`asc/cli/control.py`, `asc/control/{list,repository,snapshot}.py`,
`asc/enqueue/{instruction,plan,reader,runtime,service}.py`,
`asc/models/control/{__init__,instruction,plan}.py`, and
`tests/test_{control_git_repository,enqueue_instruction_materialization}.py`.
Added `asc/control/git.py` and `asc/state/instruction_materializations.py`.
The three deleted modules are listed above. Source/document writers and client
files were not changed.
