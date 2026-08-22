---
title: Vocabulary Cheatsheet
aliases:
  - Vocabulary
  - Control Vocabulary
---

# Vocabulary Cheatsheet

Quick reference for the controlled terms and user-facing labels used by Control.

**Core rule:** `stage` describes the **condition of the text**; `status` describes **what should happen next**. Keep those concepts separate. The configured design rule is that stage and status should not share word stems.

> [!note]- AI-processing vocabulary
> The AI-operation terms below extend the intent of `status`. `cleanup`, `rewrite`, and `verify` already exist in `vocabulary.yaml`; the other precise operation names are recommended additions. The older broad terms `edit`, `polish`, and `review` remain part of the current source-of-truth until deliberately retired or redefined.

## Frontmatter vocabulary

### Stage — condition of the text

| Key | Meaning |
|---|---|
| `raw` | Source material or first capture with little or no editorial shaping. |
| `rough` | Coherent enough to work with, but still visibly incomplete or uneven. |
| `revised` | Has undergone substantive revision and is approaching publication quality. |
| `final` | Editorially complete for the intended purpose; further changes should be exceptional. |

### Status — next operational disposition

#### Current configured values

| Key | Meaning |
|---|---|
| `write` | Create the required prose or content from source material, notes, or instructions. |
| `rewrite` | Recast existing text substantially while preserving its intended meaning or function. |
| `edit` | General editorial intervention. Useful as a broad fallback, but too unspecific for precise dispatch. |
| `cleanup` | Fix mechanical noise: typos, punctuation, obvious grammar, formatting, transcription/OCR artifacts, and similar defects. |
| `polish` | Improve already competent prose without changing its substance. Broad and subjective; prefer a more specific operation when possible. |
| `review` | Inspect and assess the text without presuming a particular kind of change. Broad; useful when the required intervention is not yet known. |
| `verify` | Check factual claims, names, dates, figures, quotations, terminology, or other assertions against reliable sources. |
| `hold` | Deliberately suspend further processing while retaining the item in the workflow. |
| `done` | No further operation is currently required. |

#### AI-processing operations

Use these when `status` is acting as a dispatch hint for the next AI/editorial operation.

| Key | Meaning |
|---|---|
| `cleanup` | Remove mechanical errors and surface noise without intentionally changing meaning or style. |
| `normalize` | Bring spelling, capitalization, dates, numbers, terminology, names, headings, formatting, and similar conventions into house style. |
| `clarify` | Resolve ambiguity, muddled logic, overcompression, awkward reference, or prose that makes the intended meaning hard to follow. |
| `tighten` | Compress sound prose by removing redundancy, weak phrasing, unnecessary qualification, and syntactic drag. |
| `rewrite` | Replace locally ineffective prose with a substantially new formulation while preserving the underlying meaning and purpose. |
| `restructure` | Reorder paragraphs, sections, argument steps, or information so the material works as a coherent whole. |
| `develop` | Add needed explanation, context, examples, transitions, support, or connective material where the text is too thin. |
| `verify` | Check claims and details that may be wrong, outdated, unsupported, or inconsistent with authoritative usage. |
| `align` | Bring the text into conformity with a brief, audience, voice, terminology set, project instruction, or professional convention. |
| `harmonize` | Make separately produced passages consistent with one another in voice, terminology, rhythm, assumptions, and level of detail. |
| `dedupe` | Detect and remove repeated ideas, facts, examples, formulations, or passages across a larger compilation. |
| `proofread` | Perform the near-final mechanical pass after substantive editing is complete; correct residual errors without reopening the prose. |
| `finalize` | Perform the final publication-readiness pass: resolve last inconsistencies and presentation defects without intended substantive revision. |

**Dispatch preference:** use the narrowest term that accurately describes the next operation. Prefer `tighten` over `edit`, `align` over `polish`, and `clarify` over `review` when the problem is already known.

### Action — provenance or explicitly requested activity

`action` is still being normalized relative to `status`; these are the currently declared values.

| Key | Meaning |
|---|---|
| `human-source` | Human-originated source material or sourcing activity. |
| `ai-draft` | Generate a draft using AI. |
| `defer` | Deliberately postpone the action. |
| `human-verify` | Assign verification to a human. |
| `human-research` | Assign research or source gathering to a human. |
| `compare` | Compare two or more passages, versions, claims, or other targets. Used by Editorial Notes. |
| `review` | General review action when a more specific action has not been assigned. Used by Editorial Notes. |

### Origin — original provenance

| Key | Meaning |
|---|---|
| `human` | The record originated with human-authored or human-supplied material. |

### Producer — producer of the current version

| Key | Meaning |
|---|---|
| `human` | The current version was produced by a human. |
| `ai` | The current version was produced by AI. |

### Writeback state

| Key | Meaning |
|---|---|
| `needs-review` | Successful AI writeback has occurred and the new version requires human review. This is the current writeback default, although it is not yet declared in `vocabulary.yaml/status`. |
| `ai` | Producer assigned after AI writeback. |

## Record vocabulary

### Content

| Record | Prefix | Meaning |
|---|---:|---|
| `passage` — Passage | `psg` | Narrative or expository text that forms part of the produced content. |
| `image` — Image | `img` | Image record or image-related content entry. |
| `section` — Section | `sec` | Composition file containing headings and ordered passage transclusions; canonical source for section structure and sequence. |

### Materials

| Record | Prefix | Meaning |
|---|---:|---|
| `topic` — Topic | `tpc` | A subject or area of investigation around which material is gathered. |
| `finding` — Finding | `fnd` | A discrete research result, fact, observation, or conclusion worth retaining. |

### Instructions

| Record | Prefix | Meaning |
|---|---:|---|
| `role` — Role | `rol` | Defines the perspective, expertise, or working role an LLM should adopt. |
| `context` — Context | `ctx` | Supplies project, subject, audience, background, or situational context. |
| `reference` — Reference | `ref` | Reusable reference material that supports an instruction or task. |
| `instruction` — Instruction | `ins` | A reusable instruction defining what should be done or how it should be done. |

### Editorial Note

| Term | Meaning |
|---|---|
| `editorial-note` | Record used to capture cross-file or higher-level editorial work rather than annotate a single span or paragraph. |
| `compare` | Default action offered for a new Editorial Note. |
| `review` | Fallback Editorial Note action. |
| `open` | Current default Editorial Note status. This is a preserved legacy value and is not presently declared in the controlled status vocabulary. |

## Annotation vocabulary

### Annotation keys

These keys state **why** text has been marked.

| Key | Label | Meaning |
|---|---|---|
| `comment` | Comment | General editorial observation that does not itself prescribe a specific operation. |
| `query` | Query | Question requiring an answer, decision, clarification, or additional information. |
| `rewrite` | Rewrite | Marked text should be substantially recast. |
| `verify` | Verify | Marked material requires factual or terminological checking. |
| `defer` | Defer | Deliberately leave the issue unresolved for later attention. |

### Annotation types

These terms state **where/how** the annotation is attached.

| Key | Label | Meaning |
|---|---|---|
| `block` | Block | Callout attached to the current paragraph. |
| `inline` | Inline | Annotation attached to selected text. |

### Directives

Directives are **not annotations**. They are fenced operational instructions embedded in a document for later processing and are handled by the dedicated Insert Directive workflow.

## Plan and instruction vocabulary

### Plan scopes

| Scope | Prefix | Meaning |
|---|---:|---|
| `standing` | `std` | Standing instruction that applies generally rather than to one task. |
| `role` | `rol` | Role instruction controlling the model's working perspective or expertise. |
| `context` | `ctx` | Context supplied to situate the work. |
| `task` | `tsk` | Instruction specific to the operation being performed. |

### Resolver properties

| Property | Payload | Prefix | Meaning |
|---|---|---:|---|
| `role` | `role` | `rol.` | Resolves role instructions into the plan payload. |
| `context` | `context` | `ctx.` | Resolves context instructions into the plan payload. |
| `specifics` | `specifics` | `spc.` | Resolves task-specific/specific instructions into the payload. |

### Plan step kinds

| Key | Meaning |
|---|---|
| `llm` | Execute a language-model processing step. |
| `script` | Execute a deterministic script or program step. |
| `rag` | Execute a retrieval-augmented generation/retrieval step. |

## Dashboard operations

| Label | Meaning |
|---|---|
| **Set Note Type** | Apply the configured type, slug prefix and template to the active note. |
| **Define Plan** | Build or edit the processing plan to be dispatched. |
| **Dispatch Run** | Send the selected material and plan into the processing pipeline. |
| **Write Responses** | Apply completed pipeline responses back to the source files. |

## Query and display vocabulary

### Status filter fields

| Key | Label | Meaning |
|---|---|---|
| `prefix` | Prefix | Filter by slug prefix/record family. |
| `folder` | Folder | Filter by vault folder. |
| `status` | Status | Filter by next operational disposition. |
| `stage` | Stage | Filter by condition of the text. |
| `class` | Class | Filter by record/content class. |

### Status sort modes

| Key | Label | Meaning |
|---|---|---|
| `slug` | Slug | Sort by stable record slug. |
| `filename` | Filename | Sort by filesystem filename. |
| `folder` | Folder | Sort/group by containing folder. |
| `prefix` | Prefix | Sort by slug prefix/record family. |
| `last_modified` | Last modified | Sort by most recent filesystem modification time. |

## Practical distinctions

### `stage` vs `status`

- **Stage:** What condition is the text in? → `raw`, `rough`, `revised`, `final`.
- **Status:** What operation should happen next? → `cleanup`, `clarify`, `verify`, `harmonize`, etc.

A `rough` passage might have status `verify`; a `revised` passage might have status `tighten`; a `raw` passage might go directly to `cleanup` or `develop`.

### `status` vs `action`

- **Status** is the current operational disposition of the file/text.
- **Action** currently mixes provenance-oriented and explicitly assigned activities (`human-source`, `ai-draft`, `human-verify`, `compare`, etc.). Its exact boundary with `status` is intentionally still under refinement.

### `cleanup` vs `proofread`

- **Cleanup** can happen early: remove mechanical noise so it does not contaminate later editorial judgement.
- **Proofread** happens late: catch residual mechanical defects after substantive work is finished.

### `tighten` vs `rewrite`

- **Tighten:** the prose works; make it leaner and stronger.
- **Rewrite:** the formulation itself is the problem; replace it substantially.

### `align` vs `harmonize`

- **Align:** conform a passage to an external target — brief, audience, project instructions, terminology, professional convention.
- **Harmonize:** conform passages to one another so the assembled work feels internally consistent.

### `clarify` vs `develop`

- **Clarify:** the necessary meaning is already present but obscured.
- **Develop:** necessary content is missing or too thin and must be added.

### `verify` vs `review`

- **Verify:** a known checking operation with an evidentiary target.
- **Review:** inspect first and decide what, if anything, needs doing.

---

*Source: current Control configuration (`vocabulary.yaml`, `records.yaml`, `annotations.yaml`, `instructions.yaml`, `workflow.yaml`, `dashboard.yaml`, `queries.yaml`, and `ui.yaml`) plus the agreed AI-processing operation vocabulary.*
