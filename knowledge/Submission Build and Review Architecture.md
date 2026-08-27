# Submission Build and Review Architecture

Treat **client/designer submission as a first-class build target** alongside web, book, and social outputs.

```text
canonical content
      │
      ├── build-site
      ├── build-book
      ├── build-social
      └── build-submit
```

## Core rule

A submission should be a **frozen, immutable external artifact**.

Working files may be overwritten internally. Anything actually sent to a client, designer, editor, or other external party should get a numbered submission ID and should never be overwritten.

Use simple project-local IDs:

```text
sub-001
sub-002
sub-003
```

Avoid encoding too much meaning into the identifier itself. Put dates, purpose, recipient, and source versions in metadata.

For example:

```yaml
submission: sub-003
purpose: designer-layout
created: 2026-08-27
source_commit: 8f4c2e1
recipient: designer
```

## Why number submissions if Git already versions the source?

Git answers:

> What did the source look like?

The submission ID answers:

> What exactly left the system?

Those are different questions.

A clean relationship is:

```text
Git commit      = source state
Submission ID   = external transaction
Returned review = response to that transaction
```

This matters when somebody later refers to “the PDF I commented on,” “the version sent last Tuesday,” or “round three.”

## Submission build

A command might look like:

```bash
build-submit hhp
```

or for selected material:

```bash
build-submit hhp Chapters/Origins.md Chapters/Growth.md
```

The resulting package might be:

```text
build/submissions/hhp/sub-003/
├── manifest.yaml
├── manuscript.docx
├── manuscript.pdf
├── source-map.json
└── assets/
```

The manifest should record exactly which source versions were included.

Example:

```yaml
submission: sub-003
project: hhp
created: 2026-08-27
format: docx

components:
  - path: Chapters/Origins.md
    version: 4f81c72

  - path: Chapters/Growth.md
    version: a81e193
```

## Supported delivery formats

The same submission build can have different output adapters:

```text
build-submit --format docx
build-submit --format pdf
build-submit --format gdrive
```

Conceptually:

```text
selected/versioned content
        ↓
submission assembly
        ↓
   ┌────┼─────────────┐
   ▼    ▼             ▼
 DOCX   PDF       Google Drive
```

Google Drive should be treated as a delivery destination, not as the authoritative version store.

## Returned material

Returned files should not overwrite the canonical source.

A designer-marked PDF might be stored as:

```text
Review/sub-003/
├── submitted.pdf
├── designer-markup.pdf
├── corrections.md
└── manifest.yaml
```

The important point is that the returned artifact stays tied to the exact submission it refers to.

This prevents ambiguity if the source manuscript has changed since the PDF was sent.

## Separate outbound and inbound operations

Keep these operations distinct:

```text
build-submit
send-submit
ingest-review
apply-review
```

Meaning:

```text
build-submit
    ↓
create frozen package

send-submit
    ↓
deliver/upload it

ingest-review
    ↓
register returned DOCX/PDF/comments

apply-review
    ↓
turn approved corrections into source changes
```

Receiving a marked-up PDF is not the same thing as accepting or applying its corrections.

## Naming convention

Good:

```text
sub-001-initial-manuscript.docx
sub-002-revised-chapters-3-5.docx
sub-003-designer-layout.pdf
sub-003-designer-markup.pdf
```

The submission number remains the stable reference. Descriptive suffixes are optional.

## Recommended rule

**Working build outputs may be overwritten. Submitted artifacts never are.**

That gives you reproducibility, clean review provenance, and a human-readable reference system without duplicating Git’s job.