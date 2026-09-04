# Service contracts

## Repository attention

`svc post-commit PATH` is the Git-hook client. It accepts one candidate
repository path, canonicalises it, and records a coalescing attention hint in
the persistent client ledger.

The message means only:

> This Git repository may deserve attention; ensure a transient session exists.

It does not assert that any editor is running or that a repository is open.
The hook does not parse or pass commit data. The dispatch daemon owns inspection
of `master` and comparison with `autoscribe/inflight`.

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

## Plan catalogue

`svc plans` is a run-once service function. It reads the published catalogue
through `asc control plans`, validates the JSON, and atomically replaces the
persistent client-side cache. Dispatch UI reads the cache without refreshing at
startup and invokes this command only through its manual refresh action.

## Recovery

The client SQLite ledger preserves repository registration and operational
attention across daemon restarts. Inflight Git commit messages and source blobs
remain the durable facts used to recover snapshots, submissions, and saved
responses.
