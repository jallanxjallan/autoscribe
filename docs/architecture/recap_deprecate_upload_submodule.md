# Recap: Deprecating the Separate Upload Submodule

## Context

The older architecture had a separate upload path for durable control assets such as instructions and plans. The pipeline also had an enqueue path for executable runs.

That distinction now looks artificial.

The project is moving toward a client/server model where a local client database will eventually hold a user-scoped snapshot of server resources. In that future model, plans are small lists of references, while run manifests are executable requests built from local/client state and submitted to the pipeline.

For the alpha phase, there is no local SQL database yet. The vault and local folders act as the authoring surface.

## New conceptual split

The durable/ephemeral split should be:

```text
Durable:
  instructions
  ledger/export/scrivener records

Ephemeral:
  plans
  run manifests
  materialized steps
  active process state
```

Instructions are worth persisting because they are reusable control assets. Plans and manifests can remain ephemeral because they are mainly authoring/execution conveniences.

## Instructions should persist

Persisting instructions is useful because each new instruction definition can generate a new identity.

If instruction content changes:

```text
same record_identity / slug
new content
new generated identity
new instruction:<identity> key
slugmap updated to point slug → new key
old key can pasture/expire
```

This gives simple update/version behavior.

The upload/ingestion shape remains NDJSON-style:

```json
{
  "record_type": "instruction",
  "record_identity": "ins.kopi-break-context.mgvcu5",
  "record_content": "Compare the Indonesia observed...",
  "scope": "context",
  "source": {...},
  "tags": {}
}
```

The persisted model stores canonical fields:

```text
type="instruction"
slug="ins.kopi-break-context.mgvcu5"
content="Compare the Indonesia observed..."
identity=<server generated>
extra metadata preserved
```

## Plans should not persist as server control assets for alpha

Plans are small reference lists.

Example plan step:

```json
{
  "index": 1,
  "kind": "llm",
  "label": "Reframe Instruction",
  "engine": "chatgpt",
  "instruction_slugs": [
    "ins.kopi-break-context.mgvcu5",
    "ins.kopi-break-framing.14owck"
  ],
  "args": {}
}
```

That is not an executable object by itself. It is a template or reference list.

The executable contract is the materialized run/step produced by the enqueuer after resolving the instruction slugs.

## Run manifests are ephemeral

A run manifest should be treated as a temporary execution request.

It may include:

```text
source content reference
prompt content
plan step references
instruction records or instruction slugs
run metadata
```

The manifest does not need to be preserved server-side after enqueue.

The enqueuer reads it, validates it, persists any durable instruction records if needed, resolves references, materializes executable steps, and pushes the call into the process chain.

## Materialized step shape

After enqueue, the worker should not need to resolve instruction slugs.

A materialized step should contain executable instruction payloads:

```json
{
  "number": 1,
  "engine": "chatgpt",
  "model": "chatgpt-stub",
  "instructions": [
    {
      "slug": "ins.kopi-break-context.mgvcu5",
      "key": "instruction:01KWABC...",
      "content": "Compare the Indonesia observed..."
    }
  ],
  "args": {}
}
```

This gives three benefits:

```text
content = worker does not resolve anything
key     = traceability to persisted instruction
slug    = human-readable audit/debug value
```

The worker remains dumb.

## Enqueue becomes the strict boundary

The enqueuer should become the single strict boundary for both durable record ingestion and executable materialization.

Its responsibilities:

```text
1. read run manifest
2. ingest embedded durable records, especially instructions
3. save/update durable records and slugmap
4. resolve instruction references through slugmap
5. materialize run-scoped call and step records
6. push call index into active zset
```

If a required instruction slug cannot be resolved, enqueue fails loudly.

If an LLM step claims to use instructions but materializes none, enqueue fails loudly.

## Deprecating `asc.upload`

The separate `asc.upload` submodule can be retired as a concept.

The useful logic should move into a more general ingestion/enqueue boundary.

Possible names:

```text
asc.ingest.records
asc.control.ingest
asc.enqueuer.records
```

The word `upload` is misleading because it implies a separate transport operation. What the system really does is ingest records.

## Unified sysadmin/user path

Sysadmin global instructions and user/project instructions should enter through the same mechanism.

User instruction:

```json
{
  "record_type": "instruction",
  "record_identity": "ins.project.foo",
  "record_content": "...",
  "scope": "project"
}
```

Sysadmin global instruction:

```json
{
  "record_type": "instruction",
  "record_identity": "ins.global.plain-english",
  "record_content": "...",
  "scope": "global",
  "owner": "sysadmin"
}
```

Same model. Same validator. Same slugmap update.

The difference is metadata and permissioning, not a separate upload mechanism.

## Testing durable components

A permanent component should not enter the system without a test.

The desired sysadmin workflow:

```text
sysadmin edits global instruction
sysadmin runs a test manifest using it
enqueue ingests/updates the instruction
enqueue runs the test
only tested durable components enter the system
```

This eliminates the old pattern:

```text
upload first, hope it works later
```

The new invariant:

```text
No permanent component enters the system except through the same path that can test it.
```

## Future client/server fit

This design also fits the later SaaS/Electron direction.

Alpha:

```text
vault files + local folders → run manifest → enqueue → materialized steps
```

Commercial:

```text
client SQLite synced catalog → run manifest → enqueue → materialized steps
```

The downstream pipeline does not need to change.

Only the manifest-building/resource-resolution layer changes.

## Final invariant

```text
Instructions persist.
Plans and manifests are authoring/execution conveniences.
Enqueue ingests durable records, resolves references, and materializes self-contained run-scoped steps.
The separate upload submodule is deprecated.
```
