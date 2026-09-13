# AutoScribe Submissions Process Reference

**Status:** Design reference  
**Date:** 7 September 2026  
**Scope:** Client-side submission/export path from Obsidian through the submissions daemon to Pandoc output

---

## 1. Purpose

The submissions process exports selected AutoScribe content into a user-facing deliverable such as DOCX, PDF, HTML, EPUB, or another Pandoc-supported format.

The design deliberately separates:

- **Obsidian interaction**
- **Git event recording**
- **submission profile discovery**
- **Pandoc asset location**
- **Pandoc execution**
- **delivery to the requested filesystem destination**

The Obsidian vault does not determine where Pandoc defaults files, filters, templates, or other publishing assets live. The **submissions daemon** owns that environment.

The user invokes **Submit Content** with a hotkey. The UI chooses a submission profile supplied by the daemon, asks for an output folder and basename, records the submission in Git, and exits. A post-commit hook summons the submissions daemon. The daemon discovers the durable submission event and performs the export.

The Git commit is the queue.

---

## 2. Design Principles

### 2.1 Obsidian is an interaction layer

Obsidian is responsible for:

- determining whether the editor state is a point or span;
- identifying the active document or selected material;
- preparing the submission source according to the established selection/flattening rules;
- displaying the daemon-provided list of submission profiles;
- prompting for output folder and basename;
- creating the submission event;
- committing it;
- triggering the post-commit summons.

Obsidian is **not** responsible for:

- finding Pandoc defaults files;
- knowing the Pandoc data directory;
- resolving filters or templates;
- deciding output format;
- assigning the output extension;
- invoking Pandoc directly;
- tracking daemon progress.

### 2.2 The submissions daemon owns the publishing environment

The daemon is responsible for:

- discovering approved Pandoc defaults files;
- publishing the current selectable defaults list;
- resolving a selected defaults identity to its actual file;
- knowing how Pandoc is installed and configured;
- invoking Pandoc;
- interpreting the defaults-defined output format;
- constructing the final output path;
- detecting and processing new submission commits;
- recording success or failure deterministically.

### 2.3 Git is the durable event store

A submission exists because a commit exists.

No additional client-side submission queue is required.

The post-commit hook is only a summons. It does not carry the work item and does not need to be reliable. If the hook invocation is lost, the daemon can later rescan the submission history and find the unprocessed commit.

### 2.4 Submission profiles are identities, not paths

The UI receives a list such as:

```json
[
  {
    "identity": "client-review-docx",
    "label": "Client Review — Word"
  },
  {
    "identity": "editorial-review-pdf",
    "label": "Editorial Review — PDF"
  }
]
```

The commit stores:

```text
defaults = client-review-docx
```

It does **not** store:

```text
/home/jeremy/.../client-review-docx.yaml
```

Filesystem layout remains an implementation detail of the daemon.

### 2.5 Output format belongs to the defaults profile

The Submit Content UI prompts for:

- output folder;
- basename.

It does not prompt for:

- extension;
- format.

The selected Pandoc defaults file determines the output format.

If the user enters:

```text
output folder: /home/jeremy/Dropbox/Review
basename: hhp-pro-bono-position-paper
```

and the selected profile is DOCX, the daemon produces the appropriate final output filename, for example:

```text
/home/jeremy/Dropbox/Review/hhp-pro-bono-position-paper.docx
```

---

## 3. High-Level Flow

```text
Obsidian
   |
   | Submit Content hotkey
   v
Determine point/span
   |
   v
Prepare submission source
   |
   v
Read daemon-published defaults list
   |
   v
Prompt:
  - submission profile
  - output folder
  - basename
   |
   v
Create submission event in Git
   |
   v
Commit to submission branch
   |
   v
post-commit hook
   |
   | summons
   v
Submissions daemon
   |
   v
Scan for unprocessed submission commits
   |
   v
Resolve defaults identity
   |
   v
Materialize/read source
   |
   v
Run Pandoc
   |
   v
Write deliverable
   |
   v
Record deterministic completion
```

---

## 4. Relationship to Dispatch Run

Submit Content should reuse **mechanics** from Dispatch Run without sharing backend semantics.

| Concern | Dispatch Run | Submit Content |
|---|---|---|
| User chooses | Plan | Submission profile/defaults |
| Additional input | Dispatch-specific | Output folder + basename |
| Durable event | Dispatch commit | Submission commit |
| Consumer | Dispatch daemon | Submissions daemon |
| Configuration source | Plans service/daemon | Submissions daemon |
| Final action | Send into AutoScribe pipeline | Produce external document |
| Branch | Dispatch/inflight mechanism | Dedicated submission branch |
| Backend meaning | Processing request | Publishing/export request |

The implementation may share UI helpers, selection helpers, commit helpers, and list display code.

It should **not** collapse plans and submission profiles into a common domain model.

---

## 5. Submission Branch

Use a branch dedicated to submissions.

The exact branch name can be selected during implementation, but it should be clearly separate from the dispatch/inflight branch.

Example conceptual name:

```text
autoscribe/submissions
```

Requirements:

- daemon-owned processing semantics;
- no interaction with `autoscribe/inflight`;
- submission commits remain durable provenance;
- commits can be scanned in order;
- processing must tolerate a daemon being stopped for an arbitrary period.

The branch is an event log, not a workspace the user edits manually.

---

## 6. Submission Event Contract

Each submission commit represents exactly one requested export.

The event must contain enough information for the daemon to execute the job without consulting transient Obsidian state.

Minimum logical fields:

```text
submission identity
source provenance
flattened/source content reference
defaults identity
output directory
basename
creation time
```

A conceptual record:

```yaml
record_type: submission
identity: <submission identity>
defaults: client-review-docx
output_dir: /home/jeremy/Dropbox/Review
basename: hhp-pro-bono-position-paper
source_vault: HHPLawFirm
source_revision: <git revision if applicable>
created_at: <timestamp>
```

The exact serialization can follow whichever lightweight record format best fits the existing Git machinery.

### 6.1 Do not store daemon implementation details

Do not put these in the submission event:

- absolute defaults-file path;
- Pandoc binary path;
- Lua filter paths;
- template paths;
- Pandoc data-directory path;
- output extension inferred by Obsidian;
- daemon socket path;
- service-unit details.

### 6.2 Source payload

The source should be the complete submission input the daemon is expected to feed to Pandoc.

The preferred boundary is a **flattened Markdown document** prepared using the established submission-selection rules.

This makes the submission event immutable and reproducible: the daemon does not need to reconstruct the user's editor selection later from a changed working tree.

If provenance information is useful, retain it separately in the submission metadata.

---

## 7. Point and Span Semantics

Submit Content should use the same fundamental editor distinction as the other Obsidian operations.

### Point

If the cursor is a point and there is no active editor selection:

- submit the active document.

### Span

If there is an active editor selection:

- submit the selected material;
- resolve the required linked/transcluded material according to the submission flattening rules;
- produce one Pandoc-ready Markdown source.

The details of flattening belong to the client-side content preparation layer, not the submissions daemon.

The daemon should receive a completed submission source, not an instruction to inspect arbitrary Obsidian files.

---

## 8. Submission Profile Discovery

The first implementation task is the submissions daemon because the UI depends on the profile list it publishes.

### 8.1 Authoritative defaults location

The daemon is configured with or otherwise owns the authoritative Pandoc submission-assets location.

This directory may contain:

- defaults files;
- Lua filters;
- reference documents;
- templates;
- metadata files;
- other Pandoc assets.

Only approved defaults files are exposed as submission profiles.

### 8.2 Stable identity

Each selectable defaults file needs a stable identity.

Recommended conceptual rule:

```text
identity = filename stem or explicit metadata identity
```

Example:

```text
client-review-docx.yaml
```

becomes:

```text
client-review-docx
```

If explicit metadata is later introduced, it can supersede filename derivation without changing the Obsidian contract.

### 8.3 Human-readable label

The daemon should expose a label suitable for the UI.

Example:

```text
identity: client-review-docx
label: Client Review — Word
```

The label may come from:

1. explicit profile metadata, if defined;
2. a lightweight naming convention;
3. a deterministic humanization of the identity.

Avoid requiring Obsidian to parse Pandoc YAML.

### 8.4 Published list

The daemon maintains a volatile list in a simple machine-readable file, analogous to the existing plan-list pattern.

Conceptual path:

```text
/tmp/autoscribe-submissions-defaults.json
```

The exact path should be centralized in the client service configuration.

Example:

```json
[
  {
    "identity": "client-review-docx",
    "label": "Client Review — Word"
  },
  {
    "identity": "editorial-review-pdf",
    "label": "Editorial Review — PDF"
  }
]
```

The file is disposable and can be rebuilt at daemon startup.

### 8.5 Refresh behavior

The daemon should refresh the list:

- at startup;
- when explicitly signalled if that is convenient;
- optionally when the defaults directory changes;
- or on a modest periodic refresh.

There is no need for elaborate filesystem watching in the first pass.

A deterministic rescan is preferable to a complex cache.

---

## 9. Submit Content UI Contract

The UI should remain small.

### Inputs

1. current point/span source;
2. daemon-published submission profiles;
3. output folder;
4. basename.

### Interaction

Conceptually:

```text
Submit Content

Profile:
  Client Review — Word

Output folder:
  /home/jeremy/Dropbox/Review

Basename:
  hhp-pro-bono-position-paper
```

Then:

```text
Submit
Cancel
```

### Validation

Before committing, the UI should minimally ensure:

- a profile is selected;
- output folder text is non-empty;
- basename is non-empty;
- basename does not contain a path separator if output folder is separate;
- source preparation succeeded.

The daemon remains authoritative for filesystem and Pandoc validation.

### Do not block on conversion

After the submission commit succeeds and the daemon is summoned, the UI can return.

The user should not have to wait for Pandoc.

---

## 10. Post-Commit Summons

The Git hook has one job:

> attract the attention of the submissions daemon.

It should not:

- parse the submission;
- resolve defaults;
- run Pandoc;
- determine whether the commit is already processed;
- mutate output state.

Conceptual flow:

```text
git commit
    |
    v
post-commit
    |
    v
signal submissions daemon
```

If signalling fails, the commit remains.

The daemon's next scan recovers the job.

This is what makes the hook a summons rather than a transport mechanism.

---

## 11. Daemon Lifecycle

The submissions daemon may run continuously as a user service, or it may use the same service architecture as the other AutoScribe client daemons.

At startup:

1. load configuration;
2. identify the Pandoc assets/defaults directory;
3. scan approved defaults files;
4. publish the profile list;
5. inspect the submissions branch;
6. identify unprocessed submissions;
7. process them in deterministic order.

On summons:

1. rescan the submission branch;
2. process any newly discovered work;
3. return to idle state.

The daemon should not assume the summons identifies a specific commit.

It should treat the signal as:

```text
There may be work. Reconcile durable state.
```

---

## 12. Detecting Unprocessed Submissions

Processing must be idempotent.

The durable submission commit is the job identity.

A submission should be considered complete only if completion state says that exact commit/identity was successfully exported.

There are several possible completion mechanisms. The implementation should use the simplest one compatible with the existing client architecture.

Acceptable patterns include:

- append-only SQLite record keyed by submission commit;
- a lightweight daemon state store keyed by submission identity;
- a dedicated processed reference if Git-only tracking is preferable.

The requirement is more important than the storage choice:

```text
same submission commit + repeated summons = at most one successful logical export
```

If the export target already exists because the previous attempt succeeded but completion recording failed, the daemon must handle that case deliberately rather than blindly duplicating output.

---

## 13. Pandoc Invocation

The daemon owns Pandoc execution.

The selected defaults identity resolves to a defaults file.

The command should remain consistent with the established AutoScribe Pandoc policy: rely on the configured Pandoc environment and defaults rather than hard-coding asset paths into Obsidian.

Conceptually:

```sh
pandoc --defaults=<resolved-defaults> <submission-source>
```

The actual command may include the required output argument or defaults-mediated values according to the final asset design.

### 13.1 Asset ownership

Pandoc assets may include:

- defaults YAML;
- Lua filters;
- templates;
- reference DOCX files;
- CSL files;
- bibliography configuration;
- metadata;
- PDF engine configuration.

All of those stay on the daemon side.

### 13.2 Output format

The daemon determines output format from the selected defaults profile.

Obsidian must not infer it independently.

### 13.3 Output filename

Inputs:

```text
output_dir
basename
defaults profile
```

Daemon derives:

```text
final extension
final output filepath
```

Example:

```text
output_dir = /home/jeremy/Dropbox/Review
basename   = hhp-law-firm-draft
format     = docx
```

Result:

```text
/home/jeremy/Dropbox/Review/hhp-law-firm-draft.docx
```

---

## 14. Output Destination Rules

The output folder comes from the user.

The daemon should:

1. expand any supported user shorthand if intentionally allowed;
2. normalize the path;
3. confirm that the destination is usable;
4. reject impossible or unsafe destinations;
5. construct the final filename;
6. invoke Pandoc;
7. confirm output exists after successful execution.

Do not silently redirect output to another directory.

### Existing output

The overwrite policy should be explicit.

A conservative first version should either:

- fail if the target already exists; or
- require a deterministic replacement policy designed in advance.

Do not make accidental overwriting the default merely because Pandoc permits it.

---

## 15. Success Record

A successful processing record should minimally associate:

```text
submission identity
submission commit
defaults identity
final output path
completion time
```

Optional useful fields:

```text
output size
Pandoc exit status
output format
```

This record is operational state, not part of the Obsidian-facing submission contract.

---

## 16. Failure Handling

Failures should be explicit and attributable to the submission identity/commit.

Useful failure classes include:

### Profile missing

The submission refers to a defaults identity no longer available.

Do not substitute another defaults file.

### Invalid output destination

The requested directory cannot be used.

### Pandoc failure

Pandoc exits non-zero.

Capture enough stderr to diagnose the failure.

### Missing asset

A defaults file refers to a template, filter, reference file, or other asset that does not exist.

### Invalid source

The committed submission source cannot be processed.

### Output collision

The intended output path already exists and the configured policy forbids replacement.

A failed submission remains a durable event and can be retried after the underlying condition is corrected.

---

## 17. Retry Semantics

Retries should operate on the same submission event.

Do not require the user to create a second commit merely because:

- a template was missing;
- Pandoc configuration was wrong;
- the destination was temporarily unavailable;
- the daemon was misconfigured.

Once fixed, summoning or restarting the daemon should allow reconciliation to retry eligible failed events.

A genuinely changed user request—different profile, basename, destination, or source—should create a new submission event.

---

## 18. Provenance

The submission commit provides durable provenance.

At minimum, it should make it possible later to determine:

- what source was submitted;
- which submission profile was selected;
- where the user requested the output;
- what basename was requested;
- when the event was created.

If the flattened source is stored directly in the commit, the exact Pandoc input can be recovered even if the source vault later changes.

That is preferable to making the daemon reconstruct historical editor state.

---

## 19. What the Daemon Must Not Do

The submissions daemon should not:

- modify the user's master content branch;
- edit the source vault;
- reinterpret Obsidian selection semantics;
- scan arbitrary vault files to reconstruct the source;
- choose a submission profile for the user;
- invent a destination folder;
- alter the requested basename without an explicit sanitization rule;
- use the dispatch/inflight branch as a submission queue;
- depend on the post-commit signal being reliable.

---

## 20. What Submit Content Must Not Do

The Obsidian operation should not:

- scan the Pandoc assets directory;
- parse the actual defaults YAML;
- run Pandoc;
- hard-code output formats;
- infer extensions;
- know template/filter paths;
- keep its own durable submission queue;
- monitor conversion progress in the first implementation;
- wait synchronously for the daemon to finish.

---

## 21. Suggested Initial Daemon Interface

The exact binary/service interface can follow the existing `svc` pattern.

Conceptually useful operations:

```text
svc submissions
svc signal-submissions <vault>
```

Possible diagnostic command:

```text
svc submissions-scan
```

The daemon process itself should reconcile all durable submission work rather than trust arguments passed through signalling.

If the common service binary already supports multiple daemon modes, submissions should be another explicit mode instead of an independent one-off script.

---

## 22. Suggested Runtime Files

Conceptual volatile state:

```text
/tmp/autoscribe-submissions-defaults.json
```

Possible signal endpoint:

```text
$XDG_RUNTIME_DIR/autoscribe-submissions.sock
```

These names are illustrative. The actual implementation should follow the current AutoScribe service naming convention.

The important distinction is:

- **Git:** durable submission event;
- **daemon state store:** durable/operational completion state;
- **/tmp:** disposable UI-facing profile list;
- **runtime socket/signal:** disposable summons.

---

## 23. Pandoc Assets Preparation

Before implementing the daemon, prepare at least one genuinely useful profile so the first end-to-end test produces a real deliverable.

Recommended first profile:

```text
client-review-docx
```

It should be capable of producing a clean Word document from representative flattened Markdown.

Prepare and manually verify:

- defaults YAML;
- reference DOCX if used;
- Lua filters if required;
- metadata defaults;
- heading behavior;
- links;
- footnotes/endnotes;
- tables;
- images if needed;
- output extension and format;
- any document title/frontmatter handling.

A second profile is useful after the first works, for example:

```text
editorial-review-pdf
```

but one working profile is enough to build the daemon contract.

---

## 24. Recommended Implementation Sequence

### Phase 1 — Pandoc assets

Create and manually test a real defaults profile outside AutoScribe.

Success criterion:

```text
known Markdown + defaults profile -> usable deliverable
```

### Phase 2 — Submissions daemon: profile discovery

Implement:

- defaults directory discovery;
- profile identity;
- label generation/metadata;
- publication of the JSON list.

Success criterion:

```text
daemon starts -> /tmp profile list contains expected profile
```

### Phase 3 — Git submission event

Define and implement the submission branch and event format.

Create a submission event manually if necessary.

Success criterion:

```text
commit alone contains everything needed to execute export
```

### Phase 4 — Daemon reconciliation

Implement:

- branch scan;
- unprocessed-event detection;
- event parsing;
- defaults resolution.

Success criterion:

```text
daemon reliably discovers a manually created submission commit
```

### Phase 5 — Pandoc execution

Implement:

- temporary/materialized source handling;
- output path resolution;
- Pandoc invocation;
- success/failure capture.

Success criterion:

```text
submission commit -> actual usable output file
```

### Phase 6 — Completion/idempotency

Implement processed-state recording.

Success criterion:

```text
repeated daemon scans do not duplicate a completed submission
```

### Phase 7 — Hook summons

Add the post-commit signal.

Success criterion:

```text
commit -> hook -> daemon reconciliation
```

while retaining recovery if signalling fails.

### Phase 8 — Obsidian Submit Content

Only after the daemon contract works:

- derive UI mechanics from Dispatch Run;
- read the published profiles list;
- prompt for output folder;
- prompt for basename;
- prepare point/span source;
- create submission event;
- commit;
- return.

---

## 25. First End-to-End Test

Use a small, real source document.

Example test:

1. Ensure `client-review-docx` appears in the published profiles list.
2. Prepare a Markdown source with:
   - title;
   - headings;
   - normal paragraphs;
   - one link;
   - one footnote;
   - representative formatting.
3. Create a submission event specifying:
   - `client-review-docx`;
   - a temporary or review output directory;
   - basename `submission-smoke-test`.
4. Commit the event.
5. Confirm the hook summons the daemon.
6. Confirm daemon discovers the commit.
7. Confirm defaults identity resolves correctly.
8. Confirm Pandoc exits successfully.
9. Confirm expected `.docx` exists.
10. Open the file and visually inspect it.
11. Summon the daemon again.
12. Confirm no duplicate export occurs.

This should be the first meaningful system test. Avoid constructing a large test harness before this basic path is known to work.

---

## 26. Later Enhancements

These are intentionally outside the first implementation but should remain compatible with the design.

### UI status

A future focused view may show:

- queued submissions;
- completed submissions;
- failures;
- output path.

### Open output

The UI could eventually offer an explicit action to open the generated file or containing folder.

### Rich profile metadata

The published profile list could later include:

```json
{
  "identity": "client-review-docx",
  "label": "Client Review — Word",
  "description": "Word document for external client review",
  "format": "docx"
}
```

`format` may be displayed as informational metadata, but the daemon remains authoritative.

### Per-profile validation

A profile could declare permitted or recommended output destinations, required metadata, or other constraints.

### Submission history

The Git event log plus daemon completion records can support a later history view without introducing a new queue architecture.

---

## 27. Architectural Summary

The final system should preserve the following boundary:

```text
OBSIDIAN
  knows:
    source
    selected profile identity
    requested folder
    requested basename

GIT
  knows:
    immutable submission event

HOOK
  knows:
    something may have happened

SUBMISSIONS DAEMON
  knows:
    defaults files
    Pandoc
    assets
    output format
    processing state
    final output

PANDOC
  knows:
    how to render the committed source using the resolved profile
```

The most important invariant is:

> **A submission commit must be sufficient for the submissions daemon to reproduce the requested export without consulting the user's transient Obsidian state.**

The second is:

> **Obsidian selects a submission profile by identity; only the submissions daemon knows where that profile and its Pandoc assets live.**

The third is:

> **The post-commit hook summons the daemon but does not transport or process the submission. Git remains the durable source of truth.**

These boundaries keep Submit Content simple, allow Pandoc assets to evolve independently of project vaults, and make the submission path recoverable and deterministic.
