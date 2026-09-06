# Canonical Control identity and enqueue revisions

Control is read directly from immutable Git objects through `asc/control/git.py`.
Enqueue resolves the configured branch once and passes that commit to plan and
instruction reads. Only selected records and their dependencies are resolved.
No checkout, extraction, Redis plan materialization, or revision fallback occurs.

## Canonical source contract

Each `plans/<identity>.json` contains one flat object with required `identity`,
`title`, `description`, `steps`, and `capabilities`, plus optional `scope`.
Plan `slug` aliases and `record_type`/`record_identity`/`record_content` envelopes
are rejected. Missing paths, invalid JSON/schema, and identity mismatches remain
distinct failures. Historical revisions are read as authored, never normalized.

Steps are keyed by consecutive string ordinals starting at `"1"`. Required fields
are `engine`, `engine_kind`, `instructions`, and `args`. Instructions contain
`role`, `context`, and `task` arrays. Kind `llm` requires `model`, `script` requires
`script`, and `rag` requires `rag_profile`; capability families cannot be mixed.
Optional fields are `label`, `temperature`, and `max_output_tokens`. Obsolete
`kind`, `index`, `instruction`, and `instruction_slugs` fields are rejected.

Capability metadata remains embedded in each plan under `engines`, `models`,
`local_scripts`, and `rag_profiles`. Enqueue requires selected declarations to
exist and checks installed execution artifacts. It does not validate capability
JSON Schemas or merge all plans for authoring validation. Git pins metadata, not
extension code. Runtime construction carries the selected component names and
arguments; the worker resolves executable files from Extensions. The retained
HHP plans declare the installed ChatGPT engine and its supported `sol` model.

Instructions remain ordinary Markdown under `instructions/` and `context/`.
Descriptive filenames require declaration lookup. Current authoring frontmatter
contains `identity`, `title`, and `description`. Opaque identities use
`(rol|ctx|tsk)_[0-9A-HJKMNP-TV-Z]{16}`. The obsolete `spc_` prefix is rejected.
Published dotted `slug` declarations remain explicitly supported for instruction
reads and materialization reloads. This is a declaration format, not a transport
envelope. Bodies are read directly from the pinned blob with whitespace intact.
The local HHP instruction bodies and frontmatter were not changed by this
follow-on migration.

## Runtime and stream boundaries

Instruction materializations receive server-generated ULIDs. Reuse requires a
matching Control identity and Git blob fingerprint and sufficient remaining TTL.
Supplied instruction sources must match the requested identity and revision.
The old Redis instruction adapter discarding transport-era `slug`,
`source_modified_ns`, and `source_size` fields was removed. Runtime readers no
longer accept `kind`, `step_number`, `number`, or `index` aliases. Scalar directive
keys remain valid runtime data; authored instruction references are arrays.

NDJSON remains the call input and administrative output protocol. It is not the
Control storage format. Existing administrative plan output retains its `slug`
field as an explicit projection from canonical `identity`; this is not an input
alias. The shared source-document/call slugmap remains outside Control lookup.

## Migration and validation boundary

All three retained HHP source plans now declare `identity`; their existing modern
steps and real capability declarations are retained. The plan template and
Control guidance use the same schema. The historical published revision contains
wrapped plans with `kind` and `instruction_slugs` and lacks capability metadata;
it must not be accepted through compatibility parsing. Publishing migrated
Control is a separate operation and was not performed.

The user waived further tests during this follow-on. Repository test changes
were not applied. Existing tests still include the superseded schema and require
updating before the suite can be treated as the current contract. Production
failure records, services, queues, and Redis state were not modified by this work.
