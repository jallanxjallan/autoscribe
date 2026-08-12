---
title: AutoScribe Service Boundaries and NDJSON
date: 2026-08-12
tags:
  - autoscribe
  - architecture
  - rust
  - pandoc
  - ndjson
---

# AutoScribe Service Boundaries and NDJSON

## Decision

The new Rust service will be **frontend-agnostic**, with Obsidian as its first client. A later Electron client will use the same service contract without changing the service core.

The service interface will use NDJSON at process boundaries. Internally, each component will use its native data structures and communication mechanisms. NDJSON is an interchange format, not an internal storage or programming model.

This design also corrects the main weakness of the existing Feeder: too many application decisions accumulated in JavaScript, where they were difficult for the project owner to inspect and challenge. In the replacement architecture, JavaScript presents state and gathers choices; Rust owns consequential behaviour.

## Core Rule

Application policy must not be hidden in an Obsidian or Electron event handler.

The project owner specifies behaviour, state transitions, ownership boundaries, and failure handling. Rust implements those decisions through an interface that can be exercised and tested without either frontend.

The frontend may:

- Display service state.
- Collect an explicit user choice.
- Send a typed command.
- Display notices, progress, results, and failures returned by the service.

The frontend must not independently decide:

- How identities are assigned.
- What constitutes a valid dispatch.
- Whether data should be uploaded or retried.
- How Git state affects an operation.
- Where records are stored.
- How remote and local state are reconciled.
- Whether a response is safe to write into a vault.

## System Boundary

```text
Obsidian adapter ─┐
Pandoc / CLI ─────┼─ NDJSON ─ Rust service
Electron adapter ─┘
```

Obsidian is the first frontend, but it is not part of the service definition. Electron can be added later as another adapter.

The service should expose the same operations through:

- A Unix socket for Obsidian and other local clients.
- Standard input and output for shell use, Pandoc integration, and testing.
- The appropriate existing network transport when communicating with the remote pipeline.

## NDJSON Rule

Each physical line is one complete typed message. Newlines inside Markdown or other text are escaped inside the JSON string, leaving the physical newline as the message boundary.

Example request:

```json
{"type":"ingest.external","identity":"01...","source_path":"/path/report.docx","source_sha256":"...","records":[...]}
```

Example acknowledgement:

```json
{"type":"ingest.accepted","identity":"01...","record_count":6}
```

At every boundary, the adapter serializes or deserializes once. JSON strings must not be passed around inside the service core or frontend application.

## Native Communication Inside Each Component

| Location | Native mechanism |
| --- | --- |
| Rust service | Typed structs, enums, function calls, SQLite transactions, Git operations, and filesystem operations |
| Obsidian | TypeScript objects and UI events |
| Electron | TypeScript objects and UI events |
| Remote pipeline | Existing Python models, Redis records, tasks, and runtime machinery |
| Process boundaries | Typed NDJSON messages over the selected transport |

## External-File Ingestion

Pandoc can be used to bring DOCX, HTML, EPUB, and other external files into AutoScribe for cleanup, classification, and eventual placement in a vault.

The intended flow is:

```text
External file
→ Pandoc conversion and preliminary labelling
→ NDJSON
→ local Rust service
→ remote cleanup/classification pipeline when required
→ local Rust service
→ reviewed and validated vault notes
```

Pandoc is responsible for document interpretation and conversion:

- Read supported external formats.
- Convert content to normalized Markdown or a Pandoc AST representation.
- Preserve useful structure such as headings, footnotes, links, tables, and metadata.
- Divide a document into candidate records when instructed.
- Apply preliminary labels derived from document structure.
- Emit typed NDJSON to the service.

Binary source files should normally be referenced by path and cryptographic hash, not embedded in NDJSON.

A Pandoc Lua filter has no native Unix-socket API, but it can call a small socket client synchronously with `pandoc.pipe()`. The preferred production arrangement is for the Rust package to supply that helper, rather than making Lua responsible for framing, timeouts, errors, or acknowledgements.

## Rust Service Responsibilities

The Rust service owns:

- NDJSON schema validation at public boundaries.
- Conversion from protocol messages into typed internal commands.
- Identity assignment and provenance.
- SQLite-backed durable local state.
- Plan and instruction resolution.
- Git state, commits, and overwrite guardrails.
- Shadow Markdown tree maintenance and DOCX sentinel relationships.
- Dispatch construction and exact-payload persistence.
- Idempotent retry using the original dispatch identity and the exact saved payload.
- Response retrieval, validation, staging, and writeback.
- External-file cleanup and classification workflow state.
- Proposed vault destinations and materialisation choices.
- Reconciliation of local and remote state.
- Typed status views, events, notices, and failures for any frontend.

The service interface should acknowledge accepted work promptly. Long-running work continues asynchronously and is observed through status queries or events. This avoids making Pandoc, Obsidian, or another client wait for a complete pipeline run.

## Idempotent Dispatch and Retry

Before transmission, the service durably saves:

- The dispatch identity.
- The complete serialized payload.
- Its hash and relevant metadata.
- The current transmission state.

If delivery is uncertain, the dashboard reports that state and asks the user to retry or cancel. A retry must reuse both the original dispatch identity and the exact saved payload. It must never reconstruct a nominally equivalent payload from current state.

This makes retry safe even when the original transmission reached the server but its acknowledgement did not return.

## Layering

The implementation should remain divided into three clear layers:

1. **Protocol** — message envelopes, message types, validation, NDJSON framing, acknowledgements, and errors.
2. **Service core** — typed Rust operations, durable state, Git, dispatch, reconciliation, and vault logic; unaware of NDJSON formatting.
3. **Adapters** — Unix socket, standard input/output, Obsidian, Pandoc helper, and later Electron.

Every important action should be callable and testable through the service interface without launching Obsidian or Electron.

## Obsidian-First Mapping

The first Obsidian adapter will map the existing interfaces onto service commands and queries:

| Obsidian interface | Service role |
| --- | --- |
| Library State | Query instruction state and request uploads |
| Define Plan | Query available components and create or update typed plans |
| Dispatch Run | Validate selection, prepare and persist a dispatch, then transmit it |
| Write Responses | Retrieve, validate, stage, write, and commit responses |
| File State | Query Git, dispatch, response, and materialisation state |
| File History | Query versions and request guarded restoration or stashing |
| System Status | Reconcile and display pending, uncertain, failed, and recoverable operations |

The JavaScript for these panels should be intentionally thin. If a behaviour cannot be explained as “display this service state” or “send this user choice,” it probably belongs in Rust.

## Consequence

AutoScribe gains one stable public language without forcing every component to work like a JSON processor. Obsidian can be replaced or supplemented without rewriting the service, Pandoc can become a general ingestion tool, and all important policy remains in a typed, testable Rust core that the project owner can specify in plain English and audit module by module.

