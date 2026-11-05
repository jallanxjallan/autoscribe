# AutoScribe v3 server ingest — revised Work Order 3

5 November 2026. Server deployment subsequently authorized by the user; client
services must remain stopped. Deployment identity/rollback details are recorded
in the release manifest and deployment journal.
Client contract: autoscribe-client commit
242dbdbc15c4ce17bd1e609debd1a6e96859c7d6 (dispatch 0.3.0).

## Inspection and scope

Engine baseline: f84484d331afdffca5ac2be15b0bd68ab2c926ef.
Templates baseline: dce9fe69f3bfb2a9c59fbead86fb5c512e1d5350.

- app/bin/asc accepts stdin via enqueue; app/autoscribe/enqueue.py validates old
  v1/v2 records and reserves durable record/call identities in enqueue_inputs.
- ssh_jobs.submit verifies package manifests, enqueues without a queue member,
  then previously launched every accepted job. execute claims running before
  preparing steps and invoking adapters. These interfaces remain unchanged.
- control.resolve_plan/materialize_plan are the authoritative SQL plan catalogue.
- The execution ledger stores calls/key references and response/export facts;
  response bodies/status live in existing Redis response hashes. There was no
  preprocessing response gate. Worker adapter errors had an Unreadable convention.
- Existing Pandoc publication filters are outside this dispatch execution path.
  Interpretation now belongs to the registered Templates Lua resource, with
  subprocess supervision in the engine. Publishing code is unchanged.
- Existing Extensions runtime/resources.py resolves assets/dropbox-bitmap;
  DropboxAssetHandler.stage performs established rclone bitmap retrieval and
  validation. This handler is reused, not copied or replaced.

## Wire and execution contracts

The exact v3 envelope remains unchanged. Required source kind/path/vault identity,
client submission/source/path/vault/raw-digest fields, safe relative paths, UTF-8,
1 MiB raw limit, encoded envelope limit, full raw SHA-256 and client record_id hash
are validated before preprocessing. record_id follows the Rust compact sorted
JSON convention, excluding record_id itself. The source-root path is not sent:
its opaque source digest is validated structurally and bound into the request,
not recomputed from an invented server-side root. Client call_id is not allocated.

Original raw Markdown remains only in the immutable request package/staging. It
is neither rewritten nor copied into Redis as a recovery snapshot. Existing
prepared execution content and generated responses still use the established
Redis payload keys; those are processing input/output, not new raw-source copies.

Pandoc Lua uses the native Markdown reader and writer. It extracts YAML metadata,
slug, plan identifier, assets and named fenced directives, then serializes the AST
body to Markdown. Normal wrapping, escaping and formatting normalization are
intentional. No raw-body slicing, source-equivalence comparison, frontmatter
reconstruction, editorial repair, duplicate-key scanner or second Markdown parser
is used. Pandoc metadata follows Pandoc's normal interpretation semantics.

The internal autoscribe.prepared.v1 result is adapted into the existing
call-content.v2 execution shape (input.content/content_sha256, Markdown format,
inline directive policy). Normalized content is not labeled as an original-body
hash. Source slug is appended to client response metadata; opaque client
coordination fields are preserved. Parsed metadata/directives and asset references
are available in execution input. Plan resolution stays in the existing catalogue.
Unknown plans and invalid required metadata are document failures; missing/broken
catalogues, Pandoc runtime/resources or dependencies are operational errors.

Declared Dropbox links use /home/jeremy/Dropbox/... or explicit dropbox:... paths.
The existing prefix mapping resolves local absolute links to the Dropbox remote;
shared bitmap staging occurs within the already verified SSH job directory.
Original links remain in asset_references, and staged asset descriptors include
paths/digests rather than binary NDJSON/Redis copies. The shared handler supports
bitmap types, not arbitrary PDF/audio assets. It adds no new vision/LLM adapter:
existing execution consumers receive the prepared input and metadata as before.
V3 stdin enqueue with declared assets requires an existing verified job directory;
the canonical SSH submit path supplies it. No new storage root or asset service is
created. Retrieval/dependency failures remain visible operational errors.

## Authoritative failure gate and receipts

Enqueue alone registers terminal preprocessing disposition. A prepared failure
has empty content, source/request identity and a diagnostic. Other document
errors use failure="Unreadable"; editorial blockers use failure="Editorial callout"
or failure="Editorial highlighting".
It materializes existing content/baggage keys with no executor queue membership,
persists an existing response hash with status=failed, and records the response
fact through the existing ledger. There is no new SQL schema or failure queue.

A completed input receipt bypasses preprocessing on replay. A Redis marker left
before the durable SQL receipt is reconciled from the already materialized call,
including failure response registration, instead of reinterpreting the document.
Malformed stdin streams are structurally validated before any prefix acceptance;
this is not a distributed transaction across operational batch failures.

The direct SSH path detects enqueue's failure outcome and never calls launch.
It uses the same response.ndjson, exports receipt and job completion mechanism.
Job state completed means transport output is ready; response status=failed and
failure=Unreadable mean processing failed. Successful responses retain
status=completed and arbitrary generated Markdown in result. Call/submission and
package identities, checksum acknowledgement and cleanup stay unchanged. The
executor also refuses any terminal preprocessing call. The legacy response
coordinator refuses to turn a failure response into a writable manuscript effect,
retaining the existing response fact and reporting through its existing errors.

V3 response extensions include source, routing and parsed metadata, alongside the
unchanged client-response.v1 schema, server call_id, result and baggage. Failure
responses retain available parsed slug/metadata without inventing absent values.

## Precise client compatibility gap — do not restart clients

The retained collector/writer contract (baseline source and installed binary
messages inspected during Work Orders 1/2) cannot consume metadata-only v3 jobs
unchanged:

1. stage_one compares response slug, source_body_sha256 and processing_sha256 to
   local jobs.slug/body_sha256/revision. The raw dispatcher stores none of these
   document-derived values. The server returns slug and metadata, but cannot
   fabricate authoritative local job state.
2. response()/apply_one also require frontmatter and jobs.original_body, and verify
   the latter against the dispatch body hash. Those manuscript copies are not
   reintroduced here. A normalized Pandoc body must never be used as the original.
3. Current collection/writeback addresses a retained path; an unambiguous ripgrep
   slug-to-path lookup is not supplied by this server change. Missing/ambiguous
   lookup must remain blocked, not select the first match.
4. Failed status must be retained/notified without processed timestamps, source
   mutation or an ordinary processing retry. The existing apply_one refuses failed
   status, but collection/terminal ownership needs the corresponding v3 adapter.

The smallest follow-up is a focused response-to-writer adapter at collection and
writeback preflight: bind returned identities/raw digest to existing dispatch
metadata, use the Git-managed target and existing staging for their established
integrity roles, resolve the returned slug unambiguously through the local index,
and pass the result through existing conflict/application checks. It must not
require generated Markdown to equal source Markdown, add a parser or Redis
manuscript snapshots, or bypass absent-original/source-conflict checks. Exact
0.1.2 writer provenance remains the prior documented uncertainty. No client code,
installation, index or writeback behavior is changed by this work order.

## Checks performed

Eight focused engine component tests cover editorial blocking/literal exclusions, v3 identities/checksums and truncated
NDJSON preflight, real Pandoc parse/write and metadata/directives, prepared normal
input and a differing generated-result fixture, failure ledger/receipt/replay
without launch/executor/effect calls, dependency errors, and the shared Dropbox
handler boundary. Asset retrieval is mocked; no cloud transfer or live execution
is claimed. One Templates catalogue test verifies resource registration. Python
syntax checks and real Lua execution cover modified runtime/configuration code.
No comprehensive suite, cross-machine, end-to-end or paid execution tests run.
Testing stopped when deployment was requested; deployment checks inspect only
release identity, runtime prerequisites, admission state and installed files.

## Installation instructions — subsequent authorization only

1. Pin the reviewed engine branch and Templates branch commits together in the
   established server release process. Preserve existing ledger/Redis data and
   job packages. Install the app source files as one engine revision and install
   the Lua resource plus resources.json in a versioned Templates revision.
2. Set TEMPLATES_ROOT to that approved absolute Templates root for AutoScribe jobs.
   AUTOSCRIBE_PANDOC defaults to /usr/bin/pandoc. This implementation was checked
   with Pandoc 3.11 and requires pandoc lua and the selected Markdown extensions.
   Missing resources or incompatible runtime fail operationally, not Unreadable.
3. Asset-bearing jobs additionally require EXTENSIONS_ROOT (or the established
   AUTOSCRIBE_EXTENSIONS_ROOT) selecting the existing shared resource release,
   its assets/dropbox-bitmap handler and image dependencies, configured Dropbox
   access, and an absolute executable AUTOSCRIBE_RCLONE (existing local-bin or
   /usr/bin/rclone fallback). DROPBOX_ASSET_ROOT retains its existing dropbox:
   default. Verify dependencies without a production dispatch.
4. Do not repoint unrelated publishing resources, change the renderer, run the
   historical broad install.sh that enables legacy daemons, unmask queue services,
   or replace the Rust dispatcher. The direct asc job interfaces remain intact.
5. Keep NUC dispatch/apply disabled/stopped until the client compatibility gap is
   reviewed and the user authorizes restart. Deployment and integration/acceptance
   testing are separate; none were performed here.
