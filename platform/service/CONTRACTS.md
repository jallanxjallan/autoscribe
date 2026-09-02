# Service contracts

## Repository attention

The local Unix socket accepts one JSON string per line. Each string is a
candidate filesystem path. `svc attention PATH...` is the reference client.

The message means only:

> This Git repository may deserve attention; ensure a transient session exists.

It does not assert that any editor is running or that a repository is open.
The worker validates and canonicalises the path and measures subsequent file
activity itself.

## Dispatch

An explicit user action creates a commit on `master` containing:

```text
Autoscribe-Plan: <published-plan-identity>
Autoscribe-Document: <source-slug>
```

The service reads the exact commit, records its source bytes on
`autoscribe/inflight`, converts those immutable sources into inline calls, and
sends the NDJSON calls to `asc enqueue`. The service neither reads nor stores a
local plan definition. Enqueue owns current Control resolution, entity
materialisation, and failure-key creation.

## Responses

The service uses:

```text
asc export list-pending
asc export extract-selected <slug> --no-receipt
asc export update-exports <result-identity>
```

It preserves the exact dispatched frontmatter, marks the reconstructed document
as an AI-produced review candidate, and commits it to `autoscribe/inflight`.
It never writes or commits `master`.

## Recovery

SQLite state is discarded on exit. Inflight Git commit messages and source
blobs are the durable facts used to recover snapshots, submissions, and saved
responses after restart.
