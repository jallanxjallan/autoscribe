# Git-Backed Selection and Dispatch Workflow

## Core Principle

Git is the durable source of truth for operational state.

Frontmatter remains user-facing editorial metadata only. It may be used to filter files in Obsidian, but it does not control dispatch, upload, or pipeline state. This avoids drift between Markdown frontmatter, Word metadata, SQLite, and the client.

Redis remains responsible only for live pipeline execution. SQLite may be used as a local cache and query index, but it should be rebuildable from Git.

## Two Obsidian Query Types

### 1. Live Editorial Queries

Live DataviewJS queries are used to work through current files.

They query only current vault state, including:

- frontmatter;
- tags;
- folders and paths;
- links;
- other Obsidian metadata.

When a file is edited and its frontmatter changes, it automatically disappears from or moves within the live query.

These queries do not interact with Git, plans, selections, uploads, or dispatch.

Their purpose is:

> What should I work on now?

### 2. Refreshable Operational Queries

Operational queries are used to create committed selections and perform uploads or dispatches.

They use the same filtering helpers as the live queries, but they are not live. They have a **Refresh** button that rebuilds the candidate list from current vault state.

This keeps the displayed selection stable while the user chooses files.

Their purpose is:

> What exact set of files am I committing and sending?

## Shared Filtering Helpers

All filtering logic should live in reusable script helpers.

Both live and operational queries should:

1. scan candidate files from scratch;
2. normalize frontmatter and metadata;
3. apply the same folder, tag, status, stage, origin, slug, and exclusion rules;
4. return data rather than render a specific interface.

The only behavioural difference is:

- live DataviewJS reruns automatically;
- operational views rerun only when the user presses **Refresh**.

This shared helper layer can later become the basis of the Electron file index.

## Git-Backed Named Selections

The user selects files, enters a human-readable label, and creates a committed selection.

Each selection has:

- an immutable internal selection ID;
- a human-readable label;
- a creation timestamp;
- a last-revised timestamp;
- a revision number;
- the exact selected paths and Git blobs;
- an associated action, such as dispatch or upload.

The UI displays the label and timestamps. Internal IDs remain hidden unless needed for diagnosis.

Example:

```text
HHP Chapter 4 — Final Line Edit
Created: 14 Jul 2026, 10:42
Revised: 14 Jul 2026, 11:08
Revision: 3
Files: 7
Status: Not dispatched
```

## Editing a Selection Before Dispatch or Upload

Before the final action, the user may:

- append files;
- remove files from the selection;
- rename the human-readable label;
- change an assigned plan where applicable.

Removing a file from a selection does not delete or revert the file itself.

Selection revisions should be append-only Git events rather than history rewrites. The original selection commit should not be amended.

Conceptually:

```text
Revision 1: A, B, C
Revision 2: append D
Revision 3: remove B
Final membership: A, C, D
```

Once dispatched or uploaded, that revision becomes immutable.

A later change creates a new revision or a new selection.

## Three Separate Operational Workflows

Content, instructions, and plans must remain separate because they have different meanings and final actions.

They may share low-level Git and UI helpers, but they should have separate views, labels, event types, validation, and commands.

---

## 1. Content Selections

### Purpose

Create a named, committed set of exact content-file versions, assign it to a plan, and dispatch it.

### Workflow

```text
Refresh candidates
→ select content files
→ enter selection label
→ choose plan
→ commit selection
→ append or remove files if necessary
→ dispatch
```

### Final action

```text
Commit and Dispatch
```

A separate **Commit Selection** action may also be offered so the user can create a selection without dispatching immediately.

### Durable dispatch identity

A dispatch refers to:

```text
selection ID
+ revision
+ selection commit
+ plan
```

The uploader exports content from the committed versions, not from the current working tree. The user may therefore continue editing after the selection is committed without changing what is dispatched.

One content selection may contain multiple files, while dispatch still creates one independent call per file.

---

## 2. Instruction Selections

### Purpose

Create a named, committed set of instruction-file versions and upload them to the instruction registry.

### Workflow

```text
Refresh instruction candidates
→ select instruction files
→ enter upload label
→ commit selection
→ append or remove files if necessary
→ upload
```

### Final action

```text
Commit and Upload Instructions
```

Instructions are versioned independently of plans and content.

An uploaded instruction revision is locked. Later edits produce another revision and another upload.

---

## 3. Plan Selections

### Purpose

Create a named, committed set of plan definitions and upload them independently.

### Workflow

```text
Refresh plan candidates
→ select plan files
→ enter upload label
→ commit selection
→ append or remove files if necessary
→ upload
```

### Final action

```text
Commit and Upload Plans
```

Plans remain independent because some plan steps do not use instructions.

A plan may define:

- ordered steps;
- engines;
- arguments;
- labels;
- optional instruction references.

The dependency direction is:

```text
Content selection → references a plan
Plan → may reference instructions
Instructions → reference neither plans nor content
```

Plan validation should allow instruction-free steps while checking that any declared instruction references resolve.

## UI Structure

The Obsidian implementation should provide three operational views:

```text
Content Dispatch
Instruction Uploads
Plan Uploads
```

Each view should contain:

- a **Refresh** button;
- candidate-file filters;
- row checkboxes;
- a human-readable selection label;
- creation and revision timestamps;
- a current-selection panel;
- append and remove actions;
- the workflow-specific final action.

The selection panel should display:

```text
Label
Created
Last revised
Revision
File count
Assigned plan, where applicable
Status
Final action timestamp
```

## JavaScript and Python Responsibilities

### Obsidian JavaScript

JavaScript handles:

- reading Obsidian metadata;
- applying user-facing filters through shared helpers;
- rendering candidate tables;
- collecting selected paths;
- displaying labels, timestamps, and returned status;
- invoking Python.

JavaScript sends intent, not authoritative state.

### Python

Python performs all authoritative operations:

1. validate repository and paths;
2. reject conflicted or invalid files;
3. verify that selected files have not changed;
4. stage only the selected files;
5. create or revise the named selection;
6. assign the plan where applicable;
7. create the Git commit;
8. export exact committed versions;
9. upload or dispatch;
10. return IDs, timestamps, commits, and outcomes.

The UI must not commit or dispatch directly.

## Git, SQLite, and Redis Boundaries

### Git

Git records durable facts:

- exact selected file versions;
- selection creation and revision;
- plan assignment;
- upload or dispatch events;
- source and result commits;
- completed writebacks.

### SQLite

SQLite may cache and index:

- selections;
- revisions;
- labels;
- paths;
- plans;
- call identities;
- upload and dispatch status.

It is not authoritative and should be reconstructible from Git.

### Redis

Redis stores only live remote execution state:

- queued;
- claimed;
- running;
- retrying;
- completed;
- failed.

It does not define durable client-side eligibility.

## Electron Migration

The Obsidian design is a direct prototype for the later Electron client.

In Electron:

- filesystem watchers and Git scanners populate SQLite;
- the shared helper logic becomes SQL-backed filtering;
- the three operational views remain separate;
- Python continues to own commit, validation, export, upload, and dispatch;
- Markdown, Word, and other file formats use the same Git-backed selection model.

Word users do not need rich frontmatter. Editorial metadata may be rudimentary or absent without affecting operational reliability.

## Final Architecture

```text
Live editorial DataviewJS
    current frontmatter and vault metadata
    automatic refresh

Refreshable content view
    named committed selection
    plan assignment
    dispatch

Refreshable instruction view
    named committed selection
    instruction upload

Refreshable plan view
    named committed selection
    plan upload

Shared filtering helpers
    one interpretation of vault metadata

Python service
    validation
    selective commit
    selection revision
    export
    upload
    dispatch

Git
    durable operational history

SQLite
    rebuildable client index

Redis
    ephemeral runtime state
```

The central object is:

> A named, timestamped, revisioned selection of exact Git file versions that remains editable until it is dispatched or uploaded.
