# Text Flagging Reference

This note records the agreed split between editorial status, production stage, text origin, and Git/repository state. The goal is to keep each field orthogonal, so selectors stay useful and no field becomes a junk drawer.

## Core model

Use four separate concepts:

```yaml
status: draft          # editorial condition
stage: notes           # production/workflow position
origin: human-written  # provenance of the current text
state: committed       # Git/repository condition, if used in frontmatter
```

If the Git condition is computed rather than stored, prefer displaying it as `repo_state` in queries, but keep the meaning the same.

## Field meanings

### `status`: editorial condition

`status` answers: **Is the text good enough?**

Suggested values:

```yaml
status: draft
status: needs-rewrite
status: needs-approval
status: approved
status: final
status: archived
```

Use `status` for judgment about the text itself: rough, weak, approved, final, obsolete, and so on.

Avoid using `status` for workflow position or provenance. For example, `ai-gen` should not be a status.

### `stage`: production workflow position

`stage` answers: **Where is this file in the work process?**

Suggested long-form default set:

```yaml
stage: notes
stage: drafting
stage: edit
stage: review
stage: layout
stage: published
```

Use `stage: notes` when rough ideas, fragments, questions, or source reminders have been entered directly into a passage file before they have become prose. This keeps `notes` out of `status`, because notes are not necessarily defective; they are simply not prose yet.

### `origin`: provenance of the current text

`origin` answers: **Where did the current wording mainly come from?**

Suggested values:

```yaml
origin: human-written
origin: ai-generated
origin: ai-assisted
origin: imported
origin: mixed
```

Recommended default for manual Obsidian templates:

```yaml
origin: human-written
```

Manual files begin as human-written because they are created by the author in the authoring environment. AI, imports, or pipeline writeback should deliberately override this value.

Use the values this way:

```yaml
origin: human-written  # written substantially by the author
origin: ai-generated   # substantially written by AI
origin: ai-assisted    # human draft revised, expanded, or reshaped by AI
origin: imported       # brought in from external source material
origin: mixed          # substantial blend with no dominant source
```

Avoid defaulting to `mixed`; it will become a junk drawer.

### `state` or `repo_state`: repository condition

`state` is reserved for Git/repository condition. Do not use it for editorial or production flags.

Suggested values, based on the current AutoScribe/Obsidian workflow:

```yaml
state: new
state: committed
state: editing
state: in-flight
state: conflicted
state: written
```

Meanings:

```yaml
new         # not yet committed
committed   # clean committed file
editing     # manually changed since last commit
in-flight   # committed file currently tagged/queued for pipeline work
conflicted  # pipeline attempted to overwrite an editing file
written     # successful AI writeback, normally followed by an automatic commit
```

If this is computed dynamically from Git rather than stored, display it in query output as `repo_state` and keep frontmatter free of Git mechanics.

## Recommended base content template

For a new manual passage file:

```yaml
---
slug: cnt.example.xxxxxx
type: content
class: passage
status: draft
stage: notes
origin: human-written
topics:
tags:
---
```

When notes become actual prose:

```yaml
status: draft
stage: drafting
origin: human-written
```

When the text needs substantial reworking:

```yaml
status: needs-rewrite
stage: edit
origin: human-written
```

When AI has produced the current wording:

```yaml
status: needs-approval
stage: review
origin: ai-generated
```

When a human draft has been reshaped by AI but still retains a human base:

```yaml
status: needs-approval
stage: review
origin: ai-assisted
```

## Variations by use case

### 1. Long-form books, reports, and corporate histories

Best for chapters, passages, sidebars, captions, case studies, and book sections.

Recommended fields:

```yaml
slug: cnt.example.xxxxxx
type: content
class: passage
status: draft
stage: notes
origin: human-written
topics:
tags:
```

Recommended `status` values:

```yaml
draft
needs-rewrite
needs-approval
approved
final
archived
```

Recommended `stage` values:

```yaml
notes
drafting
edit
review
layout
published
```

Typical progression:

```yaml
stage: notes       # fragments and ideas
stage: drafting    # becoming prose
stage: edit        # prose exists, needs shaping
stage: review      # ready for checking/approval
stage: layout      # text settled, production work
stage: published   # final output complete
```

For long-form work, keep the stage list boring and stable. The selector value should tell you where the file sits in the book-production pipeline, not how good it is.

### 2. Online posts and short web articles

Online posts often need a scheduling step that book chapters do not.

Suggested template:

```yaml
---
slug: cnt.example.xxxxxx
type: content
class: post
status: draft
stage: notes
origin: human-written
channel: web
topics:
tags:
---
```

Suggested `stage` values:

```yaml
notes
drafting
edit
review
scheduled
published
```

Suggested `status` values:

```yaml
draft
needs-rewrite
needs-approval
approved
final
archived
```

Use `stage: scheduled` only when the post is approved or final but waiting for release. Do not use `status: scheduled`, because scheduled is not an editorial condition.

### 3. Newsletter articles

Newsletters usually need an editorial flow plus a send/publication flow.

Suggested template:

```yaml
---
slug: cnt.example.xxxxxx
type: content
class: newsletter-article
status: draft
stage: notes
origin: human-written
issue:
section:
topics:
tags:
---
```

Suggested `stage` values:

```yaml
notes
drafting
edit
fact-check
review
layout
sent
published
```

Suggested `status` values:

```yaml
draft
needs-rewrite
needs-approval
approved
final
archived
```

Use `stage: fact-check` when the article is textually coherent but factual claims still need verification. If fact-checking is central, consider adding a separate field instead of overloading `status`:

```yaml
verification_status: pending
verification_status: verified
verification_status: disputed
```

This keeps `status` editorial and `verification_status` evidentiary.

### 4. Research notes and findings

For findings, provenance and verification matter more than production stage.

Suggested template:

```yaml
---
slug: fnd.example.xxxxxx
type: finding
status: draft
stage: notes
origin: imported
verification_status: pending
topic:
source_urls:
tags:
---
```

Suggested `status` values:

```yaml
draft
needs-source
needs-rewrite
needs-approval
approved
archived
```

Suggested `stage` values:

```yaml
capture
extract
verify
summarize
review
approved
```

For findings, `verification_status` is often more important than `status`:

```yaml
verification_status: pending
verification_status: verified
verification_status: disputed
verification_status: superseded
```

Suggested origin defaults:

```yaml
origin: imported       # extracted from source material
origin: human-written  # manually written analysis note
origin: ai-assisted    # human note reworked by AI
origin: ai-generated   # AI produced the finding text
origin: mixed          # blended source extraction, human note, and AI wording
```

### 5. Social posts and captions

For social material, channel and scheduling matter.

Suggested template:

```yaml
---
slug: cnt.example.xxxxxx
type: content
class: social-post
status: draft
stage: notes
origin: human-written
channel:
campaign:
topics:
tags:
---
```

Suggested `stage` values:

```yaml
notes
drafting
edit
review
scheduled
published
```

Suggested optional fields:

```yaml
channel: linkedin
campaign: launch
post_date:
```

Avoid encoding channel inside `stage`; `stage: linkedin-review` will quickly multiply into brittle selector values. Keep channel separate.

### 6. Image briefs, captions, and visual assets

For image records, the same principle works, but `origin` may refer to the asset or the caption depending on the file type. Be explicit.

Suggested template for an image/content record:

```yaml
---
slug: img.example.xxxxxx
type: content
class: image
status: draft
stage: notes
origin: human-written
asset_origin:
caption_origin: human-written
topics:
tags:
---
```

Suggested `stage` values:

```yaml
notes
brief
production
review
layout
published
```

Suggested asset-specific origin values:

```yaml
asset_origin: photo
asset_origin: commissioned
asset_origin: ai-generated
asset_origin: archive
asset_origin: mixed
```

This avoids confusion between the provenance of the image and the provenance of the caption text.

## Decision rules

Use these quick rules when setting flags:

```text
Is this about whether the text is good enough?
→ status

Is this about where the file is in the workflow?
→ stage

Is this about who or what produced the current wording?
→ origin

Is this about Git cleanliness, writeback, or pipeline conflict?
→ state / repo_state

Is this about whether claims are sourced and true?
→ verification_status

Is this about publication venue?
→ channel
```

## Values to avoid

Avoid vague or hybrid values such as:

```yaml
status: ai-gen
status: in-progress
stage: needs-rewrite
origin: draft
state: review
```

These blur the system.

Prefer precise replacements:

```yaml
origin: ai-generated
stage: drafting
status: needs-rewrite
status: draft
stage: review
```

## Minimal recommended field set by content type

### Passage / chapter section

```yaml
status: draft
stage: notes
origin: human-written
```

### AI writeback result

```yaml
status: needs-approval
stage: review
origin: ai-generated
```

### Human draft revised by AI

```yaml
status: needs-approval
stage: review
origin: ai-assisted
```

### Imported research note

```yaml
status: draft
stage: capture
origin: imported
verification_status: pending
```

### Newsletter article ready for fact-checking

```yaml
status: draft
stage: fact-check
origin: human-written
verification_status: pending
```

### Approved online post waiting to go out

```yaml
status: approved
stage: scheduled
origin: human-written
channel: web
```

## Final recommendation

For the core Obsidian content workflow, keep the canonical fields simple:

```yaml
status: draft
stage: notes
origin: human-written
```

Then let specialized content types add extra fields only when they need them:

```yaml
verification_status: pending
channel: web
issue:
section:
asset_origin:
caption_origin:
```

This keeps the main selectors clean while still allowing richer workflows for newsletters, findings, online posts, and visual assets.
