---
title: Port to Rust
slug: autoscribe.port-to-rust
type: note
kind: architecture
status: proposed
created: 2026-08-07
---

# Port to Rust

## Decision

Do not undertake a wholesale rewrite of Feeder in Rust. Instead, begin extracting the latency-sensitive infrastructure layer into a small persistent Rust core while keeping the fast-changing editorial and LLM pipeline logic in Python.

The immediate justification is practical rather than speculative: repeated Git and Redis operations are already introducing noticeable latency in the current Obsidian-based AutoScribe system. The Rust work should therefore improve the system in day-to-day use even if an Electron client is never funded or built.

## Primary Goal

Remove UI latency caused by repeated process startup, Git invocations, Redis connection setup, and small infrastructure queries.

The Rust layer should provide fast, deterministic access to:

- Git repository and file state
- file and version history
- Redis dispatch, response, failure, and transport records
- manifests and hashes
- queue and daemon state
- pipeline status diagnostics

## Architecture

The preferred architecture is daemon-based rather than having each Obsidian macro invoke Git, Redis, or Python directly.

```text
Obsidian UI
    |
    | atomic request manifest
    v
local request spool
    |
    v
autoscribe-control daemon (Rust)
    |- Git queries
    |- Redis queries
    |- filesystem state
    |- manifests and hashes
    |- dispatch/status operations
    `- result/status records

remote pipeline / Redis
    |
    v
autoscribe-retrieve daemon
    |- poll for pending completed results
    |- download responses
    |- validate downloads
    |- record failures
    `- stage responses locally
```

## UI Request Model

The UI should become deliberately thin. A macro should write a request manifest into a temporary/spool directory and return rather than launching a chain of subprocesses.

Example:

```json
{
  "request_id": "01...",
  "operation": "file-state",
  "vault": "/path/to/vault",
  "files": ["Contents/foo.md"],
  "created_at": "2026-08-07T15:52:00+07:00"
}
```

Requests should be written atomically: write a temporary file first, then rename it into the watched request directory. The daemon should only consume finalized manifests.

On Linux, the local control daemon should use filesystem notifications rather than polling the request spool.

## Daemon Split

### `autoscribe-control`

Persistent local Rust daemon responsible for fast infrastructure operations.

Initial responsibilities:

- Git status and history
- live File State queries
- live File History queries
- Redis status inspection
- manifest and hash checks
- dispatch eligibility checks
- request lifecycle tracking
- system diagnostics

The daemon may keep Redis connections and repository context warm, but diagnostic commands such as File State and File History should still perform fresh reads of authoritative Git state when requested rather than relying on stale cached results.

### `autoscribe-retrieve`

Separate daemon responsible for remote result retrieval.

Responsibilities:

- poll the pipeline/Redis for completed or pending downloadable results
- download available result payloads
- verify downloads
- stage successful responses locally
- preserve explicit failure records
- retry transport failures according to policy

A short polling interval is acceptable here because result retrieval does not require instantaneous response.

## Request Lifecycle

Every request should have an explicit state, for example:

```text
queued -> running -> completed
                  `-> failed
```

A possible spool layout is:

```text
~/.local/share/autoscribe/spool/
    requests/
    running/
    completed/
    failed/
```

This provides a durable audit trail and makes retries and System Status diagnostics straightforward. UI or process crashes should not make requests silently disappear.

## Rust/Python Boundary

### Move to Rust first

- Git inspection
- filesystem scanning
- file/repository state
- Redis queries
- persistent Redis connections
- manifests and hashing
- queue/status bookkeeping
- daemon/process supervision
- retry and transport-state infrastructure
- diagnostic aggregation

### Keep in Python

- LLM/API orchestration
- evolving pipeline logic
- instruction assembly while its schema remains fluid
- experimental workflow behavior
- local editorial/text-processing scripts unless there is a separate reason to port them

The division should be driven by stability and performance, not by a goal of eliminating Python.

## Why Not Port All of Feeder Now?

Feeder is working and still contains workflow logic that changes frequently. A full rewrite would create substantial regression risk and would consume effort without necessarily improving the working editorial system.

The Rust core should therefore accrete stable infrastructure functions one at a time. If, after those migrations, little remains in Python Feeder, completing the port can be reconsidered then.

## First Implementation Targets

1. Create `autoscribe-control` as a small Rust daemon.
2. Define a simple JSON request/result protocol.
3. Add atomic spool-directory request handling.
4. Move Git state/history queries behind the daemon.
5. Add persistent Redis connectivity and common Redis state queries.
6. Point File State and File History at the daemon.
7. Move Dispatch Run/System Status preflight queries to the same interface.
8. Add `autoscribe-retrieve` for automatic result polling and staging.
9. Preserve explicit error and failure records for every operation.

## Success Criterion

The port is successful when routine AutoScribe UI actions involving Git or Redis feel effectively immediate and the Obsidian layer no longer needs to orchestrate multiple subprocesses for infrastructure state.

An Electron product is not a prerequisite. If commercial development never occurs, this architecture should still leave the existing AutoScribe/POD publishing environment faster, more robust, and easier to diagnose.
