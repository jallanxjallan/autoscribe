---
title: Obsidian-First Client Architecture
date: 2026-07-12
status: reference
---

# Obsidian-First Client Architecture

## Decision

Build the complete selection and dispatch workflow inside Obsidian first, using standard Node.js facilities wherever possible. Keep Python as the authoritative backend. Once the workflow is stable, port the user interface to Electron without changing the backend contract.

The Obsidian implementation is not throwaway work. Its Obsidian-specific layer can later be packaged as a standalone plugin for users who prefer Markdown vaults, while the Electron client serves users working primarily with Microsoft Word and other desktop document formats.

## Core Architecture

```text
                   Python backend
             ┌──────────┴──────────┐
             │                     │
      Obsidian plugin       Electron client
      Markdown vaults       Word/docx workflow
```

Python owns the durable and operational logic:

- scan vaults and document sources;
- read git state, commit hashes, tags, and repository condition;
- parse and validate metadata;
- assemble records for display;
- validate user selections again before dispatch;
- prepare uploads and enqueue pipeline calls;
- maintain SQLite and other persistent state;
- return structured success and failure reports.

The user interface owns temporary presentation state:

- render file lists;
- display git and metadata fields;
- provide filters, checkboxes, and selection controls;
- collect the user's choices;
- send selected identifiers back to Python;
- display validation, upload, and pipeline results.

## Process Communication

Electron or Obsidian's Node environment starts a persistent Python subprocess and communicates with it using newline-delimited JSON over standard input and output.

```text
Obsidian or Electron
        ⇅ NDJSON
Persistent Python process
```

This provides immediate request-and-response communication without temporary manifests, polling directories, or filename conventions.

Example request:

```json
{
  "id": "req-17",
  "action": "list_files",
  "vault": "Articles"
}
```

Example response:

```json
{
  "id": "req-17",
  "ok": true,
  "files": [
    {
      "path": "Scenes/Corner Office.md",
      "slug": "cnt.corner-office.94vji1",
      "commit": "a14c92f",
      "tags": ["pipeline-ready"],
      "status": "draft"
    }
  ]
}
```

After the user selects files, the UI sends only stable identifiers and the version information originally displayed:

```json
{
  "id": "req-18",
  "action": "dispatch",
  "selected": [
    {
      "path": "Scenes/Corner Office.md",
      "expected_commit": "a14c92f"
    }
  ]
}
```

Python reloads and revalidates every selected file before uploading. If a file changed while the selection screen was open, Python rejects that item and asks the UI to refresh.

This prevents stale UI state from dispatching the wrong revision.

## Obsidian-First Development Sequence

### Phase 1: Python backend contract

Define a small, stable set of JSON operations, for example:

- `list_files`
- `refresh_git_state`
- `get_file_details`
- `dispatch`
- `upload_instructions`
- `upload_plans`
- `list_pending_results`
- `write_back`
- `health`

The protocol should not mention Obsidian views, Electron components, or HTML. It should describe application operations only.

### Phase 2: Obsidian interface

Use Obsidian as the first working client because the current workflow and source files already live there.

Use standard Node.js wherever possible:

- `child_process.spawn()` for the persistent Python process;
- stdin/stdout for NDJSON;
- ordinary JavaScript objects for temporary UI state;
- Obsidian APIs only for genuinely vault-specific behavior;
- minimal custom JavaScript for rendering and interaction.

The Obsidian query or view should not contain git logic, validation rules, pipeline logic, or upload logic. It should request records from Python, render them, collect a selection, and return that selection.

### Phase 3: Iron out workflow details

Use the Obsidian implementation to settle:

- the file record schema;
- filtering and sorting;
- checkbox and batch-selection behavior;
- stale-selection detection;
- error reporting;
- partial upload failures;
- retry behavior;
- user confirmation points;
- writeback presentation;
- progress and completion messages.

### Phase 4: Electron port

Replace the Obsidian view with an Electron renderer.

```text
Obsidian view              → Electron renderer
Obsidian command           → Electron button or menu
Obsidian Node bridge       → Electron main process
Python backend             → unchanged
NDJSON protocol            → unchanged
```

Electron's main process manages the Python subprocess. The renderer communicates with the main process through Electron IPC and never receives unrestricted Node access.

## Product Split

### Obsidian plugin

The packaged Obsidian plugin supports Markdown-vault users.

It handles:

- vault-relative paths;
- Obsidian commands and views;
- frontmatter-aware presentation;
- Markdown selection and writeback;
- optional links to notes and active views;
- communication with the Python backend.

It does not implement AutoScribe pipeline rules itself.

### Electron client

The Electron application supports Word and general desktop-document users.

It handles:

- `.docx` and other document-oriented interfaces;
- desktop file selection and project management;
- document-specific preview and writeback;
- installation and management of the bundled Python runtime;
- communication with the same Python backend.

### Python backend

Python is shared by both clients and remains authoritative.

```text
Obsidian knows vaults.
Electron knows desktop UI and Word files.
Python knows AutoScribe.
```

## Manifest Policy

Do not use manifest files merely to move state between the UI and Python.

Use direct IPC for:

- listing files;
- current git state;
- filters and selections;
- upload requests;
- progress reports;
- validation results.

Retain files only where durability is intentional, such as:

- audit records;
- crash recovery;
- saved selections;
- reproducible dispatch batches;
- exported results;
- debugging snapshots.

A durable record should exist because the operation must survive a crash or be reviewed later, not because two local processes need to communicate.

## Benefits

This design provides:

- one authoritative backend;
- no duplicated pipeline logic;
- fewer brittle JavaScript queries;
- no temporary-manifest naming problem;
- immediate UI/backend communication;
- safe stale-state validation;
- a low-risk path from Obsidian to Electron;
- a reusable Obsidian plugin rather than a discarded prototype;
- support for both Markdown and Word-centered users.

## Immediate Next Step

Implement a minimal persistent Python subprocess with two operations:

1. `list_files` — return vault-relative paths, slugs, metadata, git commit information, and dispatch eligibility;
2. `dispatch` — accept selected paths plus expected revision identifiers, revalidate them, prepare the upload, and enqueue the records.

Build one Obsidian view around those two operations. Expand the protocol only after that round trip works reliably.
