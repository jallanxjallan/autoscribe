# AutoScribe ingest and response architecture

## Submission and execution

Submission, response delivery and acknowledgement use SSH/SCP exclusively.
`asc job submit` validates the durable uploaded package and invokes the native
Markdown adapter. One Pandoc process runs the Templates-owned ordered Extensions
filters: metadata validation, source hints, call identity and readiness, then the
JSON interpretation writer. Original manuscript bytes are never reconstructed.
`asc enqueue` validates `autoscribe.prepared.v2`, resolves Control, and stores
Redis call content/baggage plus SQLite call/key facts without invoking Pandoc.

One canonical UUIDv4 `submission_id` identifies each operation. Ordinary `call_id`
is `call_ + SHA1(submission_id)`; preprocessing infrastructure failures retain
the deterministic UUID-derived failure identity. Execution IDs never derive from
source paths, titles, slugs or provenance. Active envelope, interpretation and
prepared records use explicit allowed fields. Unknown fields fail validation;
there are no retired-source guards, aliases, fallback source IDs or migrations.
Source identity/provenance baggage stays opaque and intact. Existing source
coordination validates paths/vaults and slug conflicts without allocating another
execution identity.

## Responses, receipts and independent output effects

The existing SSH `autoscribe.client-response.v1` contains submission/call IDs,
terminal status, exact UTF-8 body `result`, `result_bytes`, `result_sha256`, retained
baggage and optional diagnostic/source/metadata details. Failed or nonterminal
responses never authorize file writes. The client compares retained authorization
with its immutable staged request. Whole-response checksums bind verified SCP
retrieval and idempotent `asc job cleanup`.

Local updates replace the body and surgically set only `plan: ""`, `dispatch:
false` and `processed: "<local UTC application time>"`. The timestamp is durably
bound to write intent and survives interrupted completion. Unrelated frontmatter
bytes, BOM and newline conventions are preserved. Conflicts retain output; explicit
accept-with-backup applies the same workflow edit. Local creation uses separately
authorized destinations and metadata, with no update-workflow properties added.

Signed server repository effects remain independently authorized. `srv-output`
requires a successful response and signed `autoscribe.return.v1` route, then emits
`autoscribe.effect.v2`. The signed effect and `autoscribe.receipt.v2` retain both
execution IDs and full opaque baggage. The effects database stores them with the
receipt. `asc effects pending/notify` and the repository-output coordinator are
retained for this purpose. Transport-only CLI commands, polling binaries, units,
configuration and fixtures have been removed. Generic ledger `exports` facts are
retained because both SSH delivery and independent signed effects record receipts
there; they are not a response transport.

## Assets and qualification

The external manuscript `assets` field, raw links, reference interpretation and
Extensions asset handler are unchanged. Asset storage retrieval can use the
existing external provider; it is not a submission/response transport. The separate
publishing pipeline is unchanged.

Qualification uses isolated Redis/SQLite/repositories and native debug clients,
real Pandoc/Lua and synthetic script execution. Only the external SSH transfer and
launch boundary is replaced by local verified-package/receipt delivery. No paid
models, real manuscripts, migration/cutover, release packaging, deployment or
service activation is included. The final architecture correction report contains
exact commits, component counts, integration evidence and remaining limits.
