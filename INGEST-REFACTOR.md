# Prepared-call ingest refactor — 6 November 2026

Candidate development change only. No production configuration, service, release selection, or data was changed. The four repository changes are one integration unit and require separate release approval.

## Architecture and ownership

`native document/envelope → AutoScribe adapter → one Pandoc process → Templates defaults → Extensions Lua filters/writer → prepared NDJSON → asc enqueue → existing Redis/ledger/executor/export/response`

AutoScribe owns envelope validation, source retention, reader selection, process supervision, prepared-record assembly and enqueue. Templates owns `pandoc/autoscribe-ingest.yaml` (registered as `pandoc.autoscribe-ingest`). Extensions owns the ordered reusable filters and interpretation writer. Services invokes `asc ingest` for document transport; SSH job submission prepares its verified document envelope before enqueue.

The defaults order is authoritative:

1. `pandoc/filters/identity/ingest_metadata.lua`: external metadata, plan/slug validation and conflicts.
2. `pandoc/filters/identity/ingest_hint.lua`: AST-based source hints.
3. `pandoc/filters/identity/ingest_call.lua`: stable submission/call identity.
4. `pandoc/filters/identity/ingest_prepare.lua`: readiness, directives and asset references.

The custom writer `pandoc/filters/emit/ingest_interpretation.lua` emits JSON metadata. It never serializes the document back to Markdown. No filter launches another Pandoc process. Python does not duplicate the filter list.

## Source inventory and historical code

The existing NUC AutoScribe checkout was `f84484d331afdffca5ac2be15b0bd68ab2c926ef`; canonical HEAD acquired for this candidate was `b54936e2b2b583f451d0ccf70442d2e84cfe8ede`. The original checkout was preserved. Extensions had pre-existing staged deletions, also preserved; work uses isolated checkouts under the existing `~/biznet/runtime` area.

The installed reference was `ingest-v3-33876de34ca6-47819f2bc327`, with a launcher pin to Templates `47819f2bc3275760cf96879b7524f4a11e318edd`. Its `preprocess.py` invoked `pandoc lua autoscribe_ingest_v1.lua` from enqueue. The versioned monolithic script was absent from acquired canonical HEAD; it was inspected from the installed release and is not restored as a parallel implementation. Deployed source files were copied read-only for inventory. The deployed asset transport helper and SSH terminal-failure response handling were recovered into the candidate where canonical HEAD lacked them.

Historical `document_slug.lua`, `build_hint_from_inputfile.lua`, `build_file_slug.lua` and `provenance_capture.lua` remain available for unrelated workflows. This pipeline replaces their responsibilities rather than restoring their behavior: scalar conversion uses Pandoc's utilities, source discovery uses explicit original coordination, provenance is retained outside the AST, and no create-only slug generator is invoked. There is no filename-to-canonical-slug conversion.

The superseded Python semantic Git dispatcher, its socket poke, call builder and fixture launcher are retired. Legacy hook installation/reset entry points fail explicitly instead of enabling the old semantic pipeline. Frontmatter helpers remain solely for existing-source writeback guards; that body writer now preserves CRLF frontmatter bytes as well as LF.

## Document and metadata contract

Preferred incoming envelope:

```json
{"schema":"autoscribe.document.v1","submission_id":"sub_example","call_source":"client_origin","source_format":"markdown","document":"---\nplan: pln_TEST\n---\n## Heading\nBody\n","source":{},"metadata":{},"baggage":{"custom":{"keep":"*exact opaque value*"}}}
```

For existing clients, `baggage.client.source` supplies the first-class call origin and `baggage.client.submission_id` supplies the stable submission identity. Explicit top-level values must agree with those copies. Legacy `autoscribe.input.v1/v2` envelope shapes and v3 `raw_markdown` are accepted by the adapter, subject to these stable origin/submission requirements. They are not accepted by enqueue.

`source.path` is optional original coordination, validated as a safe relative path. `source.original_filename` is an optional descriptive filename and grants no writeback permission. Staging/work directories never become source paths. Supplied client coordination must agree with the retained source. `metadata.plan` and `metadata.slug`, and the existing envelope routing/source claims, supplement document fields; incompatible supplied claims fail. A supplied slug must be an ASCII identifier of 1–160 bytes matching `[A-Za-z0-9_.:/-]+`; missing slugs are valid, explicitly malformed values fail. Plans must match `pln_[A-Za-z0-9_-]+`, up to 160 bytes. The legacy `autoscribe` plan field, if supplied, must agree with the canonical plan.

The adapter supplies a namespaced `autoscribe_transport` command-line metadata value containing hex-encoded UTF-8 JSON. Hex avoids Pandoc's Markdown interpretation of metadata strings, and command-line precedence prevents document content replacing transport coordination. Other supplementary metadata fills absent document metadata. Authoritative plan/slug conflicts are checked before supplementation. The untouched envelope and opaque baggage remain outside the AST.

Source identity preference is existing slug, original filename, first nonempty AST heading at any level, first nonempty AST paragraph/plain text, then `Untitled document`. Hints collapse ASCII whitespace and are bounded to at most 160 Unicode code points. All available original coordination, slug, heading and content hint are retained under `baggage.autoscribe_ingest.source`; the namespace also records source format, origin and submission. This namespace is reserved and cannot overwrite incoming baggage. Other baggage is copied without semantic interpretation. Document `dispatch` metadata is descriptive only.

Native-reader selection is separate from downstream representation policy: Markdown, HTML and DOCX have reader mappings. Only Markdown has an implemented downstream content policy; HTML/DOCX return an explicit unsupported-representation failure. No Word/Google Docs workflow or implicit conversion is introduced. Markdown bytes, including frontmatter, BOM, links, punctuation and line endings, are retained as received UTF-8 text, not reconstructed from the AST.

## Prepared contract and runtime mapping

The single enqueue contract is `autoscribe.prepared.v2`:

```json
{"schema":"autoscribe.prepared.v2","status":"ready","record_id":"inp_<origin/submission digest>","call_id":"call_<Lua submission digest>","call_source":"client_origin","submission_id":"sub_example","plan":"pln_TEST","content":"<untouched original Markdown>","content_sha256":"<SHA-256 of original bytes>","source_format":"markdown","source":{},"baggage":{},"metadata":{},"directives":[],"asset_references":[],"references":[],"assets":[]}
```

`plan` is the sole authoritative plan ID in the prepared record. The original source payload may naturally contain editorial metadata; parsed metadata is descriptive. Enqueue validates the prepared contract and content checksum, retains the atomic duplicate safeguards, and uses the existing Control authority to resolve the explicit plan ID. It never discovers plans or interprets documents. Unknown catalogue plans produce an explicit enqueue error without entering execution.

For runtime compatibility, Redis still stores `autoscribe.call-content.v2`: the existing materialized `plan` execution object, derived `routing.plan_id`, source coordination and `input.content`. Content also records `call_id` and `call_source`. The runtime mapping is not a second prepared-call authority. Opaque baggage remains in hash `call:<call_id>:baggage`, field `json`; no source identity is moved into ledger metadata. The ledger retains calls/key references and durable enqueue fingerprints. Existing export/response envelopes reload the stored baggage intact.

## Identity and retries

Lua generates successful/preprocessed call IDs as `call_` plus `pandoc.sha1(length-prefixed origin + stable submission ID)`. This is a deterministic submission namespace; neither filename, slug, heading, manuscript content nor timestamp determines uniqueness. Different submissions of identical content use different submission IDs. Replaying an accepted submission uses the same call ID. Adapter `record_id` binds the origin/submission with SHA-256; enqueue verifies this binding and rejects a changed prepared payload for the same identity. Call IDs are opaque identifiers rather than ULIDs; existing downstream identifier checks accept them.

The existing SQLite reservation and atomic Redis marker/content/baggage/queue operation remain. Completed receipts prevent requeueing after consumption or marker eviction. The crash boundary after Redis materialization is reconciled before the durable queued receipt. An accepted preprocessing failure is terminal; correcting the document or retrying with a different interpretation requires a new submission ID.

## Failure contract and discoverability

Failures use the same prepared version with `status: "failed"` and `failure: {"code": "...", "message": "..."}`. They retain available original content, source, baggage, submission and diagnostics. Lua interpretation failures retain their Lua call ID. When Pandoc cannot run or transport validation prevents interpretation, the adapter uses a separate `failed_<origin/submission SHA-256>` diagnostic identity; this never denotes a runnable execution call.

Identifiable failures are stored through the existing call/response ledger and Redis response hashes, and exported through the existing response protocol with failed status. SSH submission uses its existing completed-transport/failed-document response path. There is no new persistent failure database. An envelope too malformed to establish an origin/submission returns its structured diagnostic to the caller, without inventing an origin or execution identity. Malformed JSON lines return `autoscribe.ingest-error.v1` with a line number; subsequent lines continue. Rust retains a transport with failures instead of deleting it, while valid siblings can be accepted and deduplicated on retry. Desktop notification behavior is inherited from the existing client response consumer; no desktop notification was exercised by the isolated tests.

## CLI and compatibility

- `asc prepare`: document-envelope NDJSON to prepared NDJSON; no Redis connection.
- `asc ingest`: document-envelope NDJSON through preparation and enqueue.
- `asc enqueue`: strictly prepared NDJSON; never invokes Pandoc.
- `asc prepare-file FILE|- --call-source SOURCE --submission-id ID`: original file/stream to prepared NDJSON.
- `asc ingest-file FILE|- --call-source SOURCE --submission-id ID`: original file/stream to enqueue acknowledgement.

File commands accept `--format`, `--source-path` and `--original-filename`. A local filename is descriptive only; a source coordination path requires the explicit option. A pathless stream gets neither an invented filename nor a path. Reader selection uses the explicit format, recognized file extension, or Markdown for a pathless stream.

Existing signed return/output baggage is preserved. A filename alone never grants in-place writeback. Existing-source writers retain their identity/conflict checks; the Python body writer preserves the original raw frontmatter. Pathless streams may use an independently authorized existing output route to create a new file. The Rust smoke exercises precisely that separation.

All raw callers must move to `asc ingest` (or prepare before enqueue). Stable origin/submission IDs are required; content-derived legacy transport IDs are not substituted for submission identities. Legacy Git-push semantic dispatch is retired. Production packaging must pin these four candidate repositories together and select the new Templates resource and Extensions filters; the old approved 11B builder is pinned to its original package and must not be run to rebuild/overwrite it. The established release approval/manifest process remains the deployment route. No candidate release package or production activation was created here. Existing deployed writer binaries must remain pinned unless separately rebuilt and qualified; this work changes Rust ingress and adds a failed-response rejection at the output boundary.

## Verification

Verified with the deployed-reference Pandoc 3.12.1 binary copied locally, isolated Redis instances with persistence disabled, temporary SQLite databases/Git repositories, fake Dropbox transport, and synthetic responses. No model API or production Redis/data was used.

- Full AutoScribe suite: 33 tests passed (including contract, all seven identity cases, plan/slug conflicts, Unicode bounds, metadata precedence, retry identity, raw CRLF preservation, structured failures, Redis/ledger/export/response and SSH compatibility).
- Rust `cargo test -p srv-input`: 5 tests passed, including raw envelope forwarding and malformed-sibling isolation.
- Templates resource catalogue: 1 test passed.
- Extensions resource catalogue: 2 tests passed.
- Targeted post-review interpretation suite: 8 tests passed; isolated CLI/Redis/Rust output suite: 4 tests passed, including rejection of failed responses before any output effect.
- Rust ingress → actual adapter/Pandoc → enqueue → isolated Redis → synthetic response → signed output → new-file Git writeback smoke passed; replay produced the same output receipt. Existing-source writeback tests passed, including a new byte-exact CRLF frontmatter check.
- `git.py diff --check` passed in all four candidate repositories.

Reproduce the Python suite with `TEMPLATES_ROOT`, `EXTENSIONS_ROOT`, `AUTOSCRIBE_PANDOC`, `PYTHONPATH=<AutoScribe>/app`, and `AUTOSCRIBE_TEST_SERVICES_BIN=<Services>/target/debug`, using `/usr/bin/python3 -B -m unittest discover -s <AutoScribe>/app/tests -v`. Build the three smoke binaries with `cargo build -p srv-input -p srv-output -p srv-writeback`; run the Rust ingress tests with `cargo test -p srv-input`. Set `PYTHONDONTWRITEBYTECODE=1`. During this work all Git operations, including those performed by fixture code, were routed through the existing `/home/jeremy/biznet/ops/git.py` wrapper using a test PATH shim.

## Modified files

### autoscribe

- `M README.md`
- `D app/autoscribe/call.py`
- `M app/autoscribe/enqueue.py`
- `M app/autoscribe/ingest.py`
- `M app/autoscribe/responses.py`
- `M app/autoscribe/ssh_jobs.py`
- `M app/bin/asc`
- `D app/daemon/dispatchd.py`
- `M app/daemon/install-post-receive.sh`
- `D app/daemon/poke_dispatch.py`
- `D app/tests/test_call.py`
- `M app/tests/test_enqueue.py`
- `M app/tests/test_ingest.py`
- `M app/tests/test_responses.py`
- `M app/tests/test_ssh_jobs.py`
- `M reset-test-fixture.sh`
- `D run-smoke-dispatch.sh`
- `D systemd/autoscribe-dispatch.service`
- `?? INGEST-REFACTOR.md`
- `?? app/autoscribe/assets.py`
- `?? app/autoscribe/preprocess.py`
- `?? app/tests/test_prepared_pipeline.py`
- `?? app/tests/test_preprocess.py`

### services

- `M README.md`
- `M bins/srv-input/src/main.rs`
- `M bins/srv-output/src/main.rs`

### extensions

- `M README.md`
- `?? pandoc/filters/emit/ingest_interpretation.lua`
- `?? pandoc/filters/identity/ingest_call.lua`
- `?? pandoc/filters/identity/ingest_hint.lua`
- `?? pandoc/filters/identity/ingest_metadata.lua`
- `?? pandoc/filters/identity/ingest_prepare.lua`

### templates

- `M resources.json`
- `M tests/test_resources.py`
- `?? pandoc/autoscribe-ingest.yaml`
