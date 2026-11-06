# AutoScribe

Document ingest is now a prepared-call boundary: the transport adapter preserves native source content, invokes Pandoc once using separately versioned defaults and Lua filters, and hands a complete `autoscribe.prepared.v2` record to `asc enqueue`. Enqueue validates and stores prepared calls without document interpretation.

See [INGEST-REFACTOR.md](INGEST-REFACTOR.md) for the schemas, filter order, CLI, identity/retry behavior, source inventory, compatibility changes and verification evidence.

This is a candidate refactor across AutoScribe, Services, Extensions and Templates. Production continues to run its approved pinned release. No deployment or activation is included. Use the established approved release process; the historical direct installer is not the release-selection mechanism.
