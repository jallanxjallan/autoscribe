---
title: AutoScribe Client-Side Markdown Processing
date: 2026-08-12
project: AutoScribe
status: architecture-decision
---

# AutoScribe Client-Side Markdown Processing

## Decision

All Markdown parsing and interpretation will take place on the AutoScribe client. The server will receive structured records and will not inspect Markdown to discover frontmatter, directives, links, transclusions, sentinels, document structure, or other client-side meaning.

For this purpose, **client** means everything running on the user's local machine. At present this comprises the Obsidian frontend and the frontend-agnostic Rust service. It also includes local supporting tools invoked by them, notably Pandoc, Lua filters, SQLite, Git, and the shadow Markdown tree.

The internal allocation of a client-side operation remains a separate design choice. An operation may belong in the Obsidian frontend, Rust service, Pandoc, or a Lua filter, provided it does not cross to the server as unparsed Markdown requiring interpretation.

## Present scope

The immediate priority is Obsidian. Importing DOCX, ODT, and other external formats is deferred. Pandoc remains the likely document engine for those formats later, but the current design should first provide a reliable local path for vault Markdown.

## Processing boundary

```text
Obsidian vault file
        ↓
local client parsing and resolution
        ↓
typed Rust values
        ↓
validated and durably saved dispatch payload
        ↓
remote pipeline
```

The client is responsible for resolving Markdown into a structured record before dispatch. This includes, as applicable:

- YAML frontmatter and record properties.
- Record content.
- Prepended ad hoc directives.
- Wikilinks and transclusions.
- Headings and document structure.
- Sentinels and shadow-chunk references.
- File-selection and intentional concatenation boundaries.
- Instruction references and dependencies.

Pandoc should be the common Markdown parser rather than reproducing Markdown interpretation in Rust. Lua filters can perform AutoScribe-specific structural extraction and transformation. Rust supervises the operation, deserializes the result into typed values, validates it, and owns durable application state.

## Directives

Directive extraction is explicitly a client responsibility.

The client should:

1. Recognize a directive by its defined Markdown structure.
2. Parse it into a typed directive value.
3. Remove the directive block from the record content sent for language processing.
4. Validate its name, target, condition, and required fields.
5. Insert it into the appropriate runtime step while constructing the dispatch payload.

A conceptual record at the local boundary is:

```json
{
  "record_identity": "psg.example.abc123",
  "content": "Markdown content without the directive block",
  "directives": [
    {
      "kind": "skip_if",
      "target": "proofreading",
      "condition": "..."
    }
  ]
}
```

The exact schema remains to be defined. The important rule is that the server receives a directive as structured data, not as Markdown that it must locate and interpret.

## Client and server responsibilities

### Client

- Understands vault Markdown.
- Resolves client-only syntax and references.
- Extracts and validates directives.
- Produces typed records.
- Resolves plans and instruction references.
- Builds and durably saves the exact dispatch payload.
- Manages SQLite state, Git guardrails, the vault, and shadow files.
- Reuses the saved dispatch identity and exact payload for an idempotent retry.

### Server

- Validates the received record schema.
- Stores and orchestrates structured calls, tasks, runtime steps, and results.
- Runs engines and server-side scripts.
- Applies already-structured directives during orchestration.
- Returns structured results.
- Does not parse Markdown or infer client-side document meaning.

The concise boundary rule is:

> **The client understands Markdown; the server processes typed records.**

## Hashes and provenance

The client should retain two distinct hashes:

- `source_sha256`: the exact bytes of the source vault file.
- `content_sha256`: the exact parsed content placed in the dispatch payload after client-only structures, including extracted directives, have been removed or resolved.

The source hash supports Git state, reconciliation, and provenance. The content hash identifies what the pipeline actually processed.

## Parallel processing

If several vault files require parsing, concurrency should be managed locally by the Rust service. Each Pandoc invocation is an independent child process. Pure parsing and validation may run concurrently through a bounded worker queue.

Durable mutation must be serialized by the affected resource:

- SQLite writes through transactions or a service-owned writer.
- Git operations per repository.
- Writes to the same vault or shadow file.
- Any shared output or media directory.

The operating rule is:

> **Parallelize pure conversion; serialize durable mutation by resource.**

Batching should happen at the Rust scheduling level. Files should normally retain independent identities, results, failures, and retries. Concatenation is appropriate only when combining selected files into one logical document is the intended editorial operation, not merely an attempt to avoid multiple Pandoc invocations.

## Architectural consequence

The Rust service remains frontend-agnostic. Obsidian is its first frontend, but a later Electron frontend can request the same local parsing and dispatch operations without changing the server protocol or relocating Markdown interpretation to the pipeline.

NDJSON remains suitable at process boundaries. It is an interchange format, not an internal representation requirement: Obsidian and Electron may use native TypeScript objects, Rust uses typed structs and function calls, and the pipeline uses its native Python models and Redis records.
