# AutoScribe prepared ingest and submission identity

Candidate implementation, amended 6 November 2026. No merge, deployment, release activation, production configuration change or production data/schema mutation is included.

## Current architecture

`document/envelope → ingest adapter → one native-reader Pandoc process → ordered Lua filters → prepared NDJSON → asc enqueue → Redis/ledger → execution/response/output`

The adapter preserves the original UTF-8 Markdown bytes and opaque baggage. Pandoc alone interprets document metadata and AST content. Enqueue validates prepared records, resolves the explicit plan through the existing Control authority, and atomically stores/deduplicates the call. No manuscript interpretation or Pandoc invocation occurs in enqueue.

Templates owns `pandoc/autoscribe-ingest.yaml`, registered as `pandoc.autoscribe-ingest`. Its ordered Extensions filters are:

1. `identity/ingest_metadata.lua`: metadata precedence, plan and optional slug validation.
2. `identity/ingest_hint.lua`: source filename, AST heading/content hints and explicit fallback.
3. `identity/ingest_call.lua`: deterministic call identity from the submission UUID.
4. `identity/ingest_prepare.lua`: readiness, directive and asset metadata.

`emit/ingest_interpretation.lua` serializes structured interpretation only. The defaults remain unchanged by the identity amendment. Rust/Python do not duplicate the filter sequence or serialize the AST back to Markdown.

## Submission identity

The sole submission identifier is a canonical lowercase RFC 4122 UUIDv4 in top-level `submission_id`. It is allocated once by the submitting operation using Python `uuid.uuid4()` or Rust `uuid::Uuid::new_v4()`. The operation durably retains that exact value and its prepared/staged request for every retry. Different submissions of identical content receive different UUIDs.

The execution identities are derived from the UTF-8 UUID string:

- Lua: `call_id = "call_" + SHA1(submission_id)`.
- Existing transport/ledger record key: `record_id = "inp_" + SHA256(submission_id)[0:32]`.
- Adapter-only preprocessing diagnostic identity, if Pandoc cannot run: `"failed_" + SHA256(submission_id)`; never runnable.

The `call_` convention and digest width remain unchanged. Enqueue validates both ID bindings. No document text, slug, path, filename, heading, plan, source provenance, timestamp, hostname, counter or client identifier participates in execution identity.

`call_source` is removed from the incoming/prepared contract, Pandoc sidecar/interpretation, generated baggage metadata, Redis call content, CLI flags and execution consumers. A new envelope containing it is rejected. `baggage.client.source` is neither required nor interpreted for execution identity; supplied opaque provenance remains intact. There is no nested-field fallback for a missing submission UUID and no compatibility path for predictable submission names or older raw-envelope schemas. No historical compatibility implementation, fixture collection or audit snapshot is retained for this amendment.

## Input and prepared contracts

Native document envelope:

```json
{"schema":"autoscribe.document.v1","submission_id":"6c99b4c3-0a5b-4fe3-aaf1-561ead771d93","source_format":"markdown","document":"---\nplan: pln_TEST\n---\n## Heading\nBody\n","source":{},"metadata":{},"baggage":{"custom":{"keep":"*opaque* 東京"}}}
```

The Rust client produces `autoscribe.input.v3` with the same top-level UUID, full `raw_markdown`, original-byte `raw_markdown_sha256`, original source coordination, and opaque baggage. Its `record_id` uses the same UUID-derived rule as the server receipt. Content integrity is carried separately by the raw-byte, staged-request and transport-package SHA-256 checksums. No submission identifier is manufactured during a transport retry.

The prepared contract remains `autoscribe.prepared.v2`, corrected before release rather than introducing a parallel version:

```json
{"schema":"autoscribe.prepared.v2","status":"ready","submission_id":"6c99b4c3-0a5b-4fe3-aaf1-561ead771d93","record_id":"inp_<UUID SHA-256 prefix>","call_id":"call_<UUID SHA-1>","plan":"pln_TEST","content":"<untouched original Markdown>","content_sha256":"<original-byte SHA-256>","source_format":"markdown","source":{},"baggage":{},"metadata":{},"directives":[],"asset_references":[],"references":[],"assets":[]}
```

`plan` is the sole authoritative prepared plan identifier. The existing materialized runtime plan object and derived `routing.plan_id` are created at the enqueue/runtime boundary. Existing SQLite reservation, exact-payload fingerprint, persistent receipt, and atomic Redis marker/content/baggage/queue safeguards remain. A changed prepared payload for an accepted UUID is rejected before overwriting or requeueing. Correcting a terminal submission requires an explicit new operation/UUID.

Redis call content now carries `submission_id` and `call_id`, never `call_source`. Opaque baggage stays in `call:<call_id>:baggage`, hash field `json`. Generic responses, pending exports and SSH client responses expose top-level `submission_id`; the Rust response stager/writer reads that field directly. There is no new alias or origin registry.

## Source semantics and boundaries

Original relative `source.path` and descriptive `source.original_filename` are optional. A filepath is never fabricated for streams; staging paths do not become original source identity. Source/baggage path and slug conflicts remain hard failures. Document plan/slug fields and externally supplied authoritative claims must agree. Transport metadata has a protected namespace and command-line precedence. Its hex-encoded UTF-8 JSON avoids Pandoc metadata Markdown-string rewriting; untouched baggage remains outside the AST.

Missing slugs are valid. Explicit slugs must match `[A-Za-z0-9_.:/-]+`, 1–160 ASCII bytes. Plans must match `pln_[A-Za-z0-9_-]+`, at most 160 bytes, without a default. Catalogue existence remains a separate existing Control check. `dispatch` document metadata is advisory only.

Identification preference is slug, original filename, first meaningful AST heading at any level, paragraph/plain-text hint, then `Untitled document`. Hints are deterministic, Unicode-safe and at most 160 code points. Available original coordination and descriptive values are retained in `baggage.autoscribe_ingest.source`. No hint becomes a canonical slug. No manuscript text, assets, links, whitespace, frontmatter or line endings are rewritten by preparation.

Markdown files/streams are implemented. The reader-selection boundary also maps HTML/DOCX, but those formats return explicit unsupported-representation failures until a downstream representation policy is defined. No conversion or new ingestion workflow is implied.

Existing signed output permissions remain independent of source filenames. Pathless streams can create new outputs through an authorized output route; in-place source writeback is never inferred. Failed responses are rejected before creating output effects. Existing-source body writers retain their conflict/slug checks and preserve raw frontmatter, including CRLF.

## Failure correlation

Identifiable preprocessing failures retain the submission UUID, original source/content/baggage and structured `failure: {code,message}` diagnostics. When Lua runs, its deterministic `call_` ID is retained even for a non-runnable failure. If transport validation or Pandoc execution prevents interpretation, only the separate `failed_` diagnostic identity is used. Neither case enters the normal execution queue.

Input lacking a valid UUID returns `autoscribe.ingest-error.v1`, without an invented call or record ID. Malformed NDJSON lines produce per-line transport diagnostics; subsequent submissions continue. Rust retains failed transports and forwards valid siblings independently. Stored failures use the existing Redis response and ledger/export paths, not a new persistent database.

## Ledger and billing audit

The AutoScribe ledger schema and its call/key/response/export methods are unchanged. Read-only inspection of the deployed `/home/jeremy/Data/ledger.sql`, `/home/jeremy/Data/control.sql` and `/var/lib/autoscribe/effects.sqlite` table definitions found no `call_source` requirement or billing table requiring that field. No billing-specific `call_source` consumer was found in the audited application/Services sources. No billing records or manuscript records were inspected or modified.

No migration, backfill, dummy value, storage rewrite or alternate reader is required for the audited current schema. Ledger facts remain keyed by opaque `call_id` and Redis references. This conclusion covers the inspected code and database definitions; no separate billing system is claimed to have been tested.

## Entry points and retry use

- `asc submission-id` allocates a new UUIDv4 locally, without Redis or Pandoc.
- `asc prepare` / `asc ingest` consume native document-envelope NDJSON; callers supply the saved UUID.
- `asc enqueue` accepts only prepared NDJSON, without allocating identities or interpreting documents.
- `asc prepare-file FILE|- --submission-id UUID` and `asc ingest-file FILE|- --submission-id UUID` accept files or streams. Optional `--format`, `--source-path` and `--original-filename` remain.
- Rust `autoscribe-dispatch --request ...` allocates a UUID only after checking for an existing unresolved reservation, saves it atomically in the current jobs/source-coordination state, and stages exact request bytes before sending. Status polling, retry and interrupted-upload recovery reuse the reservation and staged bytes.
- Services ingress and SSH `job submit` consume existing UUIDs; they do not generate replacement IDs.

For CLI use, allocate and save the UUID once before delivery, then reuse the saved value and prepared record. Do not place a fresh generator invocation inside a delivery-retry loop. The default-file/stream commands require an explicit UUID to make accidental retry regeneration impossible.

## Verification and release scope

Verified locally using Pandoc 3.12.1, disposable Redis/SQLite/Git state, candidate Rust binaries, fake Dropbox and synthetic responses:

- 40 Python regression/integration checks: UUID shape/random generation, missing/malformed IDs, origin independence, deterministic calls/failures, accepted-payload conflicts, exact Markdown/baggage preservation, Redis/ledger/export/response, SSH and writeback.
- 3 Rust Services ingress tests: unchanged raw forwarding without origins, malformed-sibling isolation and per-record body limits.
- 3 Rust dispatcher component tests plus 1 transport-library test passed; the live SSH transport test remained disabled.
- 3 Rust writer integration checks passed for response staging, persistence, source conflicts, reconciliation and Git-failure recovery using top-level response submission IDs.
- All Rust-client targets compile with the locked dependency set. Existing alias-target/dead-code warnings remain; no new release binary was installed.
- Native Rust submitter → immutable staged v3 bytes → one Pandoc invocation → enqueue/Redis smoke passed, including source edits after staging, identical retry receipts and matching client/server `record_id`.
- Rust ingress → prepared call → synthetic response → signed new-file output and repeat receipt checks passed. Failed output effects are rejected.

The initial sandbox run could not create local sockets; rerunning only those test checks with loopback access resolved the environment restriction. No model calls, production Redis tests, source-data changes, merge or deployment occurred.

Changes remain on the existing AutoScribe #2, Services #5 and Extensions #5 branches. Templates #13's defaults/order need no code change. The user-approved client fix remains on `codex/finalize-raw-dispatch-20261105` in `autoscribe-client`. These contracts must be reviewed and pinned together before any separately authorized release.

## SSH/local writer correction — 6 November 2026

The SSH `autoscribe.client-response.v1` exporter now supplies `result_bytes` and
`result_sha256` for the exact UTF-8 body, alongside existing UUID/call identity,
terminal status and retained baggage. The paired Rust candidate consumes
`autoscribe.output-operation.v1` authorization from durable job state and the
immutable raw request. Updates preserve raw frontmatter; creates use separately
authorized metadata and destinations. No retired source/processing checksum or
copied frontmatter is fabricated. The original integration-review execution
safety corrections and their regression tests are included in this candidate.

Submission, response delivery and local file effects use SSH/SCP exclusively.
Services' legacy Dropbox response exporter is outside this implementation and
unchanged. The direct signed repository-output smoke is separate from client
local creation. No model calls, production manuscripts, service activation,
release packaging or deployment are part of this correction. The final
consolidated report records test counts, limitations and candidate commit SHAs.
