# AutoScribe Service

`autoscribe-service` provides UI-agnostic dispatch and response daemons plus
small run-once client commands. It knows Git repositories, Markdown files,
dispatch commits, `autoscribe/inflight`, Pandoc, `asc enqueue`, and
`asc export`. It contains no editor-specific discovery or state.

## Commands

```sh
svc post-commit /absolute/path/to/repository
svc dispatch
svc responses
svc plans
svc dispatch-once /absolute/path/to/repository
svc status
svc scan /absolute/path/to/repository [...]
```

`svc post-commit` is the Git-hook client. It canonicalises the repository,
records a coalescing attention hint in the client ledger, and returns without
performing dispatch work. The hook passes only the repository path.

`svc dispatch` drains persistent attention hints and reconciles matching
commits from `master` against durable records on `autoscribe/inflight`.
`svc responses` reconciles pending exports for known repositories.

`svc plans` is a run-once refresh that writes the published plan catalogue
atomically to `$XDG_CACHE_HOME/autoscribe/plans.json` (or
`$HOME/.cache/autoscribe/plans.json`). It is intended for an explicit UI
refresh action and is not a startup daemon.

`svc scan` is the one-pass diagnostic form. It does not use the attention
ledger, but it does perform normal dispatch and response reconciliation.

## Repository sessions and activity

The client SQLite ledger keeps the repository registry, coalescing attention
hints, and operational observations across daemon restarts. Git remains the
durable recovery authority for source snapshots and submission receipts.

## Ownership boundaries

- `master` is user-owned and read-only to the service.
- `refs/heads/autoscribe/inflight` is service-owned.
- Plans and instructions are authored and published by Control, not stored or
  validated by this service.
- A dispatch commit carries a plan identity and document identities.
- `asc enqueue` resolves/materialises the published plan and its referenced
  entities, producing pipeline failure state when resolution fails.
- Response candidates are reconstructed from the exact inflight source and
  written only to inflight for later user review.

The worker records a submitted Git event only after `asc enqueue` exits
successfully. UI actions can still return immediately because submission runs
inside this background service.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `AUTOSCRIBE_ASC` | `asc` | Pipeline CLI executable |
| `AUTOSCRIBE_PANDOC` | `/usr/bin/pandoc` | Pandoc executable |
| `AUTOSCRIBE_PANDOC_DISPATCH_DEFAULTS` | `~/Work/Extensions/pandoc/defaults/dispatch.yaml` | Static dispatch defaults; runtime input and plan use a second temporary defaults file |
| `AUTOSCRIBE_WORKER_POLL_MS` | `250` | Dispatch/response poll interval |
| `AUTOSCRIBE_CLIENT_DB` | `$HOME/.local/share/autoscribe/service.sqlite` | Client ledger |

A post-commit adapter must only pass a candidate repository path. It must not
inspect commit trailers or implement Git, dispatch, or response logic.
