# AutoScribe Service

`autoscribe-service` is one permanent, UI-agnostic system worker. It knows Git
repositories, Markdown files, dispatch commits, `autoscribe/inflight`, Pandoc,
`asc enqueue`, and `asc export`. It contains no editor-specific discovery or
state.

## Commands

```sh
svc worker
svc attention /absolute/path/to/repository [...]
svc scan /absolute/path/to/repository [...]
```

`svc worker` owns a user-scoped Unix socket and waits safely with no registered
repositories. A UI adapter periodically calls `svc attention`; the path is only
a candidate hint. The worker canonicalises it, requires the path to be a Git
root, and then owns all scanning and reconciliation.

`svc scan` is the one-pass diagnostic form. It does not use the attention
socket, but it does perform normal dispatch and response reconciliation.

## Repository sessions and activity

Repository sessions are transient working memory. Each pass:

1. drains new attention hints;
2. expires quiet sessions after the configured TTL;
3. visits repositories in descending rolling activity score;
4. scans meaningful Markdown changes and global slug integrity;
5. reconciles dispatch commits;
6. reconciles pending exports.

New, removed, or renamed Markdown files add more activity than a modification.
Repeated writes with unchanged bytes add nothing. Scores decay every pass, so
recent distinct work wins without allowing autosave chatter to dominate.

The in-memory SQLite schema is structured process memory only. Git is the
durable recovery record.

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
| `AUTOSCRIBE_PANDOC_FILTER` | platform emit filter path | NDJSON emit filter |
| `AUTOSCRIBE_WORKER_POLL_MS` | `2000` | Worker pass interval |
| `AUTOSCRIBE_REPOSITORY_TTL_SECS` | `3600` | Quiet-session expiry |
| `AUTOSCRIBE_SERVICE_SOCKET` | `$XDG_RUNTIME_DIR/autoscribe-service.sock` | Attention socket |

An adapter must only discover candidate repository paths and send attention.
It must not implement scanning, activity scoring, Git, dispatch, or response
logic.
