---
title: AutoScribe Import, Submit, Export, and Service Architecture Recap
date: 2026-09-10
status: reference
scope: AutoScribe client architecture
---

# AutoScribe Import, Submit, Export, and Service Architecture Recap

## Purpose

This note captures the architecture decisions made on September 10, 2026 around importing text, submitting composition documents, exporting through Pandoc, and simplifying the long-running Rust services.

The governing principle is:

> **Everything in its lane.**

Obsidian remains an editor and a convenient place to initiate authoring actions. Long-running state awareness belongs in Rust daemons. Explicit, comparatively infrequent document transformations belong in Rust commands or small standalone utilities. Word processors and other commercial applications remain responsible for their own final-format export tools.

---

# 1. Separate Stateful Services from Explicit Transformations

The main architectural distinction is between operations that require continuous awareness of changing state and operations that can be run explicitly against a snapshot.

## Stateful operations

### Dispatch

Dispatch happens frequently and depends on current local and remote state. It therefore belongs in a daemon.

The dispatch daemon needs awareness of:

- current repository state;
- current Control state;
- available plans;
- pending dispatch records;
- inflight state;
- server/runtime state;
- failures and retries;
- the exact source version captured for each dispatch.

### Writeback

Writeback also happens frequently and must compare current source state with the state captured when content was dispatched.

It therefore remains a daemon.

The writeback daemon is responsible for:

- receiving or detecting completed responses;
- locating the exact dispatch source;
- confirming whether automatic writeback is safe;
- refusing to overwrite diverged material;
- applying valid responses;
- committing writeback results;
- recording failures or review-required outcomes.

## Explicit operations

### Import

Import is comparatively infrequent and can be invoked deliberately.

It should therefore be a command, not a watcher or daemon in the power-user workflow.

Import may be sophisticated because it runs synchronously and does not have to remain resident:

- parse external formats;
- normalize document structure;
- assign identities/slugs;
- create shadow Markdown;
- resolve references;
- infer metadata;
- handle attachments;
- perform deterministic conflict checks.

### Export

Export is also comparatively infrequent and should be explicit.

It belongs in a Rust command or a small standalone Rust GUI.

Export may:

- select a frozen submission;
- select a Pandoc defaults file;
- assemble a composition from versioned Git objects;
- run Pandoc;
- write the resulting artifact to Dropbox, Google Drive, a website tree, or another destination.

There is no reason for export to be a daemon.

---

# 2. Commercial-User Import Model

For ordinary commercial users, the user-facing workflow can remain simple.

A client configuration can define one or more external document folders. The user creates or places files there. AutoScribe imports those files and creates corresponding Markdown working representations.

Conceptually:

```text
commercial document
        |
        v
     import
        |
        v
shadow / canonical Markdown
        |
        v
AutoScribe processing
```

The commercial application remains responsible for its own output facilities:

- Save As;
- DOCX;
- PDF;
- print;
- layout;
- presentation formatting.

AutoScribe should not reproduce a word processor's export machinery.

For the power-user workflow, however, import should be explicitly invoked from the command line rather than continuously watched.

---

# 3. Obsidian Is Not the Control Plane

The new architecture should avoid putting substantial workflow machinery into Obsidian.

Obsidian may still provide an editing convenience such as a Submit button, but it should not own:

- Git branch management;
- Pandoc invocation;
- export configuration;
- state reconciliation;
- daemon logic;
- current remote awareness;
- document compilation.

This avoids coupling AutoScribe to Obsidian's internal state.

---

# 4. Wikilinks and Deterministic Resolution

A central problem is that Obsidian can resolve ambiguous wikilinks using its continuously maintained metadata cache.

An external service reading a file or manifest cannot safely reproduce that behavior from static text alone.

Therefore AutoScribe should not depend on Obsidian's live link-resolution cache after submission.

## Rule

At the automation boundary, references must become deterministic.

For submission purposes, wikilinks are resolved into **vault-relative filepaths**.

For example:

```markdown
[[Mahahari]]
```

may resolve to:

```markdown
[[Contents/Cases/Mahahari.md]]
```

or, when display text is needed:

```markdown
[[Contents/Cases/Mahahari.md|Mahahari]]
```

The external processing system should never have to guess which file a bare ambiguous wikilink meant.

## Important distinction

Ordinary authoring may still use friendly wikilinks.

Submission converts those references into deterministic, vault-relative paths.

---

# 5. Submit Is a Very Small Obsidian Operation

The Submit UI should be intentionally narrow.

The user provides only:

```text
tag
```

The Submit action determines whether the user has:

- an active selection; or
- no selection, in which case it uses the current document.

The button captures the selected/current content and records the submission request on `master`.

It should not:

- choose output formats;
- choose an output location;
- invoke Pandoc;
- manage the `submits` branch;
- flatten included files;
- perform long-running processing.

Conceptually:

```text
submit(tag, current_file, selection?)
```

---

# 6. Submission Documents Are Composition Documents

The submitted material will often contain a mixture of:

- headings;
- ordinary prose;
- transitional text;
- links;
- embedded/transcluded files.

Therefore the virtual submission object is not merely a manifest.

It is better understood as a **composition document**.

The composition document is valid Markdown in its own right. Its prose and headings should pass through into final output.

References that mean "insert this document here" should become explicit include instructions rather than ordinary links.

Example:

```markdown
# Banking Crisis

The crisis transformed the firm's banking practice.

::: {.include path="Contents/Advising IBRA.md"}
:::

This experience would become important later.

::: {.include path="Contents/Mahahari.md"}
:::
```

The ordinary text remains content.

The `.include` nodes are composition instructions.

## Submit-time transformation

The Submit machinery should distinguish:

```text
ordinary text              -> copied unchanged
headings                   -> copied unchanged
ordinary wikilink          -> resolved to vault-relative filepath
embedded/transcluded file  -> converted to explicit include node
```

The composition document is therefore a frozen statement of:

- what prose should appear;
- what headings should appear;
- where external document components should be inserted.

---

# 7. Do Not Flatten at Submit Time

Submit should resolve identity and references, but should not flatten all linked content into one giant Markdown file.

Flattening should happen structurally during Pandoc processing.

Reasons:

- included files retain their own structure;
- headings can be adjusted in the AST rather than by textual hacks;
- later filters can operate on the assembled document;
- composition remains inspectable;
- components remain individually traceable;
- the submission remains reproducible.

Thus:

> **Submit creates a frozen composition document. Export compiles it.**

---

# 8. Git Branch Responsibilities

The important correction made during the discussion is that **Obsidian Submit writes only to `master`**.

The Rust process owns the operational submission branch.

## Master

Obsidian creates the submission request/record on `master`.

That record captures:

- the tag;
- current-file context;
- selection or full-document content;
- enough information for the Rust process to reconstruct the submission.

Obsidian does not touch the `submits` branch.

## Submits branch

The Rust submission process reads the request from `master` and creates its own immutable commit on `submits`.

That commit contains the exact content that was actually submitted.

This mirrors dispatch.

Conceptually:

```text
Obsidian
   |
   v
master commit
   |
   `-- submission request
       |-- tag
       |-- composition source
       `-- source context

Rust submission process
   |
   v
resolve exact source state
resolve wikilinks
collect referenced files
build virtual composition document
   |
   v
submits branch snapshot commit
```

---

# 9. Submission Snapshots Should Mirror Dispatch

The submission lifecycle should follow the same philosophy as dispatch.

The Rust process should read the target material from the authoritative source state and place the exact versions used into its own branch.

The resulting submission commit is an immutable record of what left the working environment.

Conceptually:

```text
master / working source state
        |
        |-- composition text
        |-- Contents/A.md
        |-- Contents/B.md
        `-- Materials/C.md
                |
                v
        submits snapshot commit
                |
                |-- composition document
                |-- Contents/A.md
                |-- Contents/B.md
                `-- Materials/C.md
```

Later changes on `master` must not alter that submission.

The invariant is:

> **A submission commit permanently contains the exact textual inputs used to produce the output.**

The downstream export process reads only from the frozen submission snapshot.

---

# 10. Git and Pandoc Under the Hood

The composition document is passed to Pandoc as a stream.

The referenced files remain Git objects in the immutable submission commit.

Conceptually:

```text
submission commit
       |
       |-- virtual composition document
       `-- frozen referenced files
                |
                v
          Rust export process
                |
                |-- read composition
                |-- spawn Pandoc
                |-- write composition to stdin
                `-- provide repo + commit identity
                              |
                              v
                         Pandoc AST
                              |
                         include filter
                              |
                     read component from
                     same Git commit
```

## Initial composition input

Rust retrieves the virtual composition document from Git and writes its bytes to Pandoc's standard input.

No temporary Markdown file is required.

## Include expansion

Pandoc parses the composition stream into its AST.

When a Lua filter encounters:

```markdown
::: {.include path="Contents/Advising IBRA.md"}
:::
```

the filter reads that exact path from the same immutable Git commit.

Conceptually the Git operation is:

```bash
git show <submission-commit>:Contents/Advising\ IBRA.md
```

The returned Markdown is parsed with `pandoc.read()`.

The include node is then replaced by the included document's AST blocks.

So:

```text
Div(include)
```

becomes:

```text
Header(...)
Para(...)
Para(...)
...
```

at the exact marked location in the parent document.

---

# 11. Why AST Inclusion Is Better Than Concatenation

The included content becomes part of the Pandoc AST rather than being pasted as raw text.

This allows later filters to operate on one coherent document structure.

For example:

```text
include.lua
    |
    v
heading normalization
    |
    v
cross-reference handling
    |
    v
caption processing
    |
    v
project-specific filters
    |
    v
Pandoc writer
```

This is particularly useful for heading management.

Included documents may contain headings whose levels need adjustment relative to where they are inserted.

That is much easier and safer in the AST than by concatenating text before parsing.

---

# 12. Include-Filter Rules

The Lua include filter should remain generic and narrow.

Its responsibility is:

> When an explicit AutoScribe include node contains a vault-relative path, load the corresponding Markdown object from the specified Git snapshot, parse it, and substitute its AST blocks at that location.

It should not expand every filepath or ordinary hyperlink.

Only explicit include nodes have composition semantics.

The resolver should enforce a few hard rules:

- vault-relative paths only;
- no absolute paths;
- no `../` traversal outside the allowed tree;
- missing targets fail deterministically;
- recursive include cycles are detected;
- all reads are pinned to one immutable commit;
- included-file frontmatter is either discarded or handled according to a deliberate policy.

Example cycle to reject:

```text
A.md -> B.md -> C.md -> A.md
```

---

# 13. Rust Runs Pandoc Internally

The export command should be the orchestration layer.

The user-facing CLI can be as simple as:

```bash
asc export <submit-tag> <defaults-file> <output-file>
```

or, in the GUI model described later:

```text
submit tag
defaults file
output folder
output basename
```

Rust performs the rest:

1. resolve the submit tag to one immutable submission commit;
2. locate and load the composition document;
3. spawn Pandoc;
4. write composition Markdown to Pandoc stdin;
5. pass repository and immutable commit context to the filters;
6. invoke the selected defaults file;
7. direct Pandoc to the required output pathname;
8. capture Pandoc status and diagnostics.

A simplified internal model is:

```text
asc export TAG DEFAULTS OUTPUT
        |
        v
       Rust
        |
        |-- resolve TAG -> commit
        |-- load composition
        |-- spawn pandoc
        |     |-- --defaults DEFAULTS
        |     |-- --output OUTPUT
        |     `-- stdin <- composition
        |
        `-- execution context:
              repo
              immutable submission commit
```

The defaults file determines the Pandoc output format and production recipe.

Therefore a separate format argument should not be necessary.

---

# 14. Composition Data Versus Execution Context

A useful separation is:

```text
document content   -> Pandoc stdin
execution context  -> environment / process arguments
```

The composition Markdown should not need to contain repository configuration.

The Rust process can pass values such as:

```text
AUTOSCRIBE_REPO
AUTOSCRIBE_COMMIT
```

to the Pandoc process.

The Lua filter uses those values when loading included files.

The commit should be resolved to an immutable hash before Pandoc starts.

Do not let the filter follow a moving branch name during compilation.

Thus, if `submits` advances during the run, the active export remains pinned to exactly the commit it began with.

---

# 15. Git Access from Lua

The simplest first implementation is for Lua to invoke Git using `pandoc.pipe()`.

Conceptually:

```lua
local source = pandoc.pipe(
    "git",
    {"-C", repo, "show", commit .. ":" .. path},
    ""
)
```

Then:

```lua
local doc = pandoc.read(source, "markdown")
return doc.blocks
```

There is no need initially to build a custom Git library or helper service.

A helper command could be introduced later if central validation becomes useful, but the initial implementation should remain small and deterministic.

---

# 16. Export GUI

A workable Rust GUI exists and the export operation is small enough that a tiny standalone application is appropriate.

The GUI should not be connected to Obsidian.

It is simply another frontend to the same Rust export core used by the CLI.

The desired interface is:

```text
Submission      [ pending-submit-tag       v ]

Defaults        [ client-docx.yaml          v ]

Output folder   [ ~/Dropbox/Clients/HHP ] [Browse]

Basename        [ hhp-client-review          ]

                                [ Export ]
```

## Required controls

### Submission tag

A list of pending/unprocessed submission tags.

### Defaults file

A list of available Pandoc defaults files.

### Output folder

A point-and-click native folder chooser.

Typical destinations may include:

- Dropbox;
- Google Drive;
- website directories;
- client delivery directories;
- arbitrary local paths.

### Output basename

A text field.

The extension can be derived from the defaults/output format where appropriate.

## Implementation approach

A lightweight Rust GUI toolkit such as `egui`/`eframe` is suitable.

A native file-dialog crate can provide the folder picker.

The GUI should call the same Rust export function as the CLI.

Conceptually:

```text
                 export core
                /           \
          CLI frontend    GUI frontend
                \           /
             resolve submission
             run Pandoc
             stream composition
             report result
```

No Obsidian hooks.

No export daemon.

No duplicated export implementation.

---

# 17. Pending Submission State Should Mirror Dispatch

Do not determine whether a submission is pending by checking whether some external output file exists.

External output paths are not authoritative state.

Files may be:

- renamed;
- moved;
- deleted;
- copied;
- synchronized elsewhere;
- overwritten.

Instead, submission/export state should mirror dispatch.

Git remains authoritative.

Conceptually:

```text
Dispatch                        Submission / Export
--------                        -------------------
master request                  master submit request
operational dispatch branch     submits branch
pending dispatch                pending submission
processed dispatch              processed submission
failure state                   failure state
immutable sent snapshot         immutable submitted snapshot
```

The exact branch/tag/status mechanism should reuse the existing dispatch lifecycle wherever practical rather than introducing a second unrelated state machine.

---

# 18. Important Clarification: Who Writes Which Branch

This is the final branch ownership model from the discussion.

## Obsidian

Writes only to:

```text
master
```

The Submit button records user intent.

## Rust submission process

Reads the new submit request from `master`.

It owns:

```text
submits
```

It resolves source material and creates the immutable snapshot there.

## Rust export process

Reads only from the immutable submission snapshot when compiling output.

This preserves the same boundary already established for dispatch:

> **The editor records intent. External Rust machinery owns operational state and immutable delivery snapshots.**

---

# 19. Planned Service Consolidation

When implementing the revised Rust services, fold the current **plans daemon into the dispatch daemon**.

A separate plans service is no longer justified.

Dispatch already needs current plan/Control awareness in order to perform its job.

The desired long-running services therefore move toward:

```text
dispatch daemon
    |-- plan awareness
    |-- pending dispatch awareness
    |-- current Control state
    |-- dispatch execution
    `-- dispatch lifecycle

writeback daemon
    |-- response awareness
    |-- source comparison
    |-- safe writeback
    `-- writeback lifecycle
```

Import and export remain explicit processes rather than daemons.

This continues the general simplification principle:

> **Only keep a daemon when the operation genuinely requires persistent awareness of changing state.**

---

# 20. Resulting High-Level Architecture

```text
                    AUTHORING

           external docs       Obsidian
                |                 |
                |                 | Submit(tag)
                v                 v
             asc import         master
                |                 |
                v                 | submit request
          canonical Markdown      |
                |                 |
                +--------+--------+
                         |
                         v

                  STATEFUL SERVICES

                dispatch daemon
                |-- plans
                |-- Control state
                |-- dispatch state
                `-- immutable dispatch snapshots

                writeback daemon
                |-- responses
                |-- safety/state comparison
                `-- writeback


                    SUBMISSION

                Rust submit process
                         |
                  reads request from master
                         |
                  resolves composition
                  resolves wikilinks
                  captures exact sources
                         |
                         v
                    submits branch
                  immutable snapshot
                         |
                         v

                      EXPORT

                 CLI or tiny Rust GUI
                         |
                select submit tag
                select defaults
                select output folder
                enter basename
                         |
                         v
                   Rust export core
                         |
                  composition -> stdin
                         |
                         v
                       Pandoc
                         |
                  Lua include filter
                         |
              Git blobs from same commit
                         |
                         v
                    assembled AST
                         |
                     filters/writer
                         |
                         v
             DOCX / PDF / HTML / etc.
```

---

# 21. Core Invariants

The implementation should preserve these invariants.

1. **Obsidian does not own operational branch logic.**

2. **Submit from Obsidian takes only a tag.**

3. **Selection wins; otherwise the current document is submitted.**

4. **Obsidian records submission intent on `master`.**

5. **Rust owns the `submits` branch.**

6. **Wikilinks are converted into deterministic vault-relative paths before downstream processing depends on them.**

7. **The virtual submission object is a composition document, not merely a filename manifest.**

8. **Ordinary prose and headings in the composition document are real output content.**

9. **Only explicit include nodes cause external Markdown components to be inserted.**

10. **Submission does not flatten included files.**

11. **The `submits` snapshot contains the exact component versions used for the submission.**

12. **Exports read only from the immutable submission snapshot, never from mutable master or the live vault.**

13. **The composition document is streamed to Pandoc through stdin.**

14. **Included components are read from Git by immutable commit ID.**

15. **Included Markdown is parsed into Pandoc AST blocks and inserted structurally.**

16. **Pandoc defaults determine the production recipe and output format.**

17. **CLI and GUI share one Rust export core.**

18. **External output files do not determine submission state; repository state does.**

19. **Submission lifecycle should mirror dispatch lifecycle.**

20. **Plans awareness is folded into the dispatch daemon.**

21. **Import and export remain explicit commands/utilities, not daemons.**

---

# 22. Likely Weekend Implementation Sequence

A sensible implementation order is:

1. **Consolidate services**
   - fold plans into dispatch;
   - preserve writeback as the other stateful daemon.

2. **Define the master-side submit record**
   - tag;
   - source file;
   - selected text or whole-document representation;
   - source commit/worktree context as needed.

3. **Implement Rust submit ingestion**
   - detect pending submit records on master;
   - resolve wikilinks deterministically;
   - transform embeds into explicit include nodes;
   - gather exact referenced files;
   - create immutable `submits` snapshot commits.

4. **Define submission lifecycle**
   - pending;
   - operational snapshot created;
   - exported/handled;
   - failure;
   - mirror dispatch mechanics wherever possible.

5. **Implement Pandoc include filter**
   - read explicit include path;
   - fetch path from immutable Git commit;
   - parse with Pandoc;
   - insert AST blocks;
   - detect missing files and include cycles.

6. **Implement Rust export core**
   - tag -> submission commit;
   - composition -> Pandoc stdin;
   - defaults -> Pandoc arguments;
   - output pathname;
   - propagate diagnostics and exit status.

7. **Expose CLI**
   - minimal command-line wrapper around the export core.

8. **Add standalone GUI**
   - pending submission dropdown;
   - defaults dropdown;
   - output-folder picker;
   - basename field;
   - Export button.

---

# 23. Immediate Practical Decision

For current work, existing material can be exported manually.

There is no need to extend the present Obsidian submission/export machinery before the Rust redesign.

The weekend implementation can therefore start from the simplified architecture above rather than preserving the older Submit Content / Pandoc defaults-picker design.

The architecture has now reduced to a clear division:

> **Obsidian captures authoring intent. Git records immutable source state. Rust owns stateful operations and explicit orchestration. Pandoc owns document compilation. Lua performs structural inclusion. Commercial applications own their own final-format export tools.**
