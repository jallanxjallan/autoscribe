# AutoScribe

Document ingest is now a prepared-call boundary: the transport adapter preserves native source content, invokes Pandoc once using separately versioned defaults and Lua filters, and hands a complete `autoscribe.prepared.v2` record to `asc enqueue`. Enqueue validates and stores prepared calls without document interpretation.

See [INGEST-REFACTOR.md](INGEST-REFACTOR.md) for the schemas, filter order, CLI, identity/retry behavior, source inventory, compatibility changes and verification evidence.

This is a candidate refactor across AutoScribe, Services, Extensions and Templates. Production continues to run its approved pinned release. No deployment or activation is included. Use the established approved release process; the historical direct installer is not the release-selection mechanism.

The registered `smoke-test` extension verifies the existing Control plan's exact
five-line sentinel/role/context/task/input protocol. It emits the original verified
bytes on success and no stdout on failure; it never invokes a model or network.
Release preparation validates every canonical script step against its packaged,
relocated executable registry and records the dependency hashes in the manifest.

`release.py --common /absolute/path/to/common ...` requires a clean, committed
Biznet Common checkout. It archives the commit and copies `python/biznet_common`
into the release's `app` directory alongside `autoscribe`. The manifest records
the full Common commit, and the release identifier includes its prefix.
For source-only development, put Common's `python` directory and AutoScribe's
`app` directory on `PYTHONPATH`. A packaged release loads both packages from
its own `app` directory.

`install-release.py` is the reviewed immutable-release installer. It retains
private staging modes until extraction is complete, sets only each public release
root to 0755, checks traversal as `jeremy` before atomic publication, and verifies
the engine entry point as that runtime user before changing active links. Child,
credential, backup and private staging modes are not recursively relaxed.


## Package A execution ownership

Only `asc job` owns execution. Intake registers prepared calls without scheduling
resident queues. The resident executor/worker source, units and direct installer
are retired. Script invocation remains registered executable stdin/stdout until
Package B. Common alone resolves models, credentials and provider requests.

An accepting job records its immutable executable and selected resource environment
in its existing package directory. A changed selection is rejected; it is never
silently rebound. SQLite owns the accepted-to-running claim. After an uncertain
provider/process outcome, running work is never automatically repeated. A stored
terminal response can be repackaged after interrupted delivery without execution.

Build with the existing `release.py` from clean committed dependency checkouts.
The manifest records exact source commits, origins, source archives and hashes,
client protocol, toolchain, native binaries, scripts and pinned resource hashes.
The selected wrapper verifies the installed payload and resources before import.
`install-release.py` checks quiescence, preserves existing Control and ledger,
and changes only the app selection and CLI binding. CLI follows the app selection;
Services/Control ingestion and Plan Manager keep independent valid bindings.
No source checkout or historical release is searched at runtime. Rollback requires
explicitly selecting a retained immutable app release with submissions quiescent.
