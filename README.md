# AutoScribe

Document ingest is now a prepared-call boundary: the transport adapter preserves native source content, invokes Pandoc once using separately versioned defaults and Lua filters, and hands a complete `autoscribe.prepared.v2` record to `asc enqueue`. Enqueue validates and stores prepared calls without document interpretation.

See [INGEST-REFACTOR.md](INGEST-REFACTOR.md) for the schemas, filter order, CLI, identity/retry behavior, source inventory, compatibility changes and verification evidence.

This is a candidate refactor across AutoScribe, Services, Extensions and Templates. Production continues to run its approved pinned release. No deployment or activation is included. Use the established approved release process; the historical direct installer is not the release-selection mechanism.

The registered `smoke-test` extension verifies the existing Control plan's exact
five-line sentinel/role/context/task/input protocol. It emits the original verified
bytes on success and no stdout on failure; it never invokes a model or network.
Release preparation validates every canonical script step against its packaged,
relocated executable registry and records the dependency hashes in the manifest.

`install-release.py` is the reviewed immutable-release installer. It retains
private staging modes until extraction is complete, sets only each public release
root to 0755, checks traversal as `jeremy` before atomic publication, and verifies
the engine entry point as that runtime user before changing active links. Child,
credential, backup and private staging modes are not recursively relaxed.
