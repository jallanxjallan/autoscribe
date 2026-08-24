# Commercial Research Provenance Layer

## Core idea

The verification system can become part of the commercial deployment rather than remain an internal editorial mechanism.

The product is not simply a vector database. It is a pipeline that converts **human-supplied research material into reusable, traceable evidence objects** and then carries that provenance into generated or edited prose.

The commercial chain is:

```text
user-supplied source material
    ↓
structured evidence objects
    ↓
claim / fact tags
    ↓
verification state
    ↓
provenance ledger
    ↓
source-traceable content
```

## 1. Ingest whatever the customer already has

The client should accept the formats people actually use:

- Markdown
- Word documents
- spreadsheets
- CSV files
- PDFs
- copied notes
- reports
- interviews / field notes
- local research files
- other structured or semi-structured source material

The system then:

- extracts text, tables, figures, entities, dates and numbers;
- divides material into sensible evidence chunks;
- records source metadata;
- hashes the source or source span;
- embeds and indexes the material;
- stores it in the evidence database.

The original human-supplied material remains the authority.

## 2. The agent asks for missing context

Raw source material is often ambiguous.

The system should notice unresolved references or unclear data and ask the user targeted questions, for example:

> Does “the company” mean the operating subsidiary or the parent company?

> Is this figure for the calendar year or the fiscal year?

> Is this number an estimate, an audited value, or an internal planning figure?

> Does this abbreviation refer to the same organisation mentioned elsewhere?

The answers become additional structured context attached to the evidence.

This is particularly valuable because it captures knowledge that is normally present only in the researcher's head.

## 3. Build fact and evidence records

Once the source material has enough context, the system can generate persistent evidence records.

For example:

```yaml
evidence_id: EV910
source: employment-data.xlsx
sheet: Workforce
cell_range: B14:D14
source_hash: 9f37...
entities:
  - Plant A
date: 2025
tags:
  - employment
  - workforce
```

A factual claim can then have its own record:

```yaml
fact_id: F184
status: verified
evidence:
  - EV910
```

These objects live in the database, not as microscopic research files.

## 4. Generate provenance tags on demand

The system should support several ways of using those fact records.

### On-demand mode

The user selects a sentence or paragraph and asks:

```text
Verify and tag this.
```

The system retrieves relevant evidence, verifies support, and returns:

```text
The plant employed about 1,400 people in 2025.
{fact:F184 status=verified evidence=EV910}
```

### Passage mode

The user can ask the system to:

```text
Tag every factual assertion in this passage.
```

The system detects claims, retrieves evidence, verifies them and inserts the appropriate markers.

### Export mode

The system can generate a separate provenance-tag file for copying into another editor or pipeline.

Possible formats include:

- Markdown
- JSON
- CSV
- NDJSON

This keeps the commercial service portable and avoids coupling it to Obsidian or any single client application.

## 5. The tags carry verification through the editorial lifecycle

Once attached to prose, the fact tag becomes workflow state.

The pipeline can:

- confirm that the evidence record still exists;
- confirm that the source hash still matches;
- detect whether the sentence has materially changed;
- invalidate verification after significant rewriting;
- re-run verification where necessary;
- prevent submission while unresolved fact states remain.

For example:

```text
Production reached 120,000 tonnes in 2024.
{fact:F027 status=verified evidence=EV893}
```

If an editing model changes it to:

```text
Production doubled to 120,000 tonnes in 2024.
```

the source may support the production figure but not the claim that production doubled.

The system should therefore downgrade the fact to something like:

```text
{fact:F027 status=needs-reverification}
```

Verification belongs to the claim, not merely to the tag.

## 6. Human-sourced data becomes a durable asset

This is the main commercial advantage.

Much valuable information does not exist cleanly on the public web:

- interviews;
- internal spreadsheets;
- government handouts;
- local editor research;
- company data;
- unpublished reports;
- field observations;
- corrections from knowledgeable people;
- regional knowledge;
- historical notes.

Normally this material gets consumed during one writing job and then effectively disappears into prose.

With the provenance system, it becomes a reusable evidence layer.

```text
human research
    ↓
structured evidence
    ↓
persistent provenance
    ↓
many future documents
```

That makes human research significantly more valuable because it becomes reusable infrastructure rather than disposable prompt material.

## 7. Separation of responsibilities

A useful commercial architecture is:

```text
Customer / researcher
    supplies facts and context

System
    preserves provenance
    indexes evidence
    detects ambiguity
    retrieves relevant material
    verifies claim support

Writer / LLM
    turns evidence into prose

Pipeline
    maintains verification state
    invalidates altered claims
    blocks unresolved facts
    preserves the provenance ledger
```

This is important because the model is not being asked to invent authority.

The authority remains the human-supplied evidence.

AI performs:

- extraction;
- retrieval;
- ambiguity detection;
- questioning;
- matching;
- writing;
- verification;
- workflow control.

## 8. What the product can legitimately claim

The service should not be marketed as proving that something is objectively true.

A customer can still provide incorrect information.

The stronger and more defensible claims are:

> **Verified against supplied evidence.**

> **Source-traceable factual provenance.**

> **This statement can be traced to the exact material supplied by the organisation or researcher.**

The system can establish:

- where the purported fact originated;
- which exact evidence supported it;
- whether that evidence has changed;
- whether the current prose still matches the evidence;
- when and how verification occurred;
- what processing version performed the verification.

It cannot guarantee that the original source itself was truthful.

## 9. Commercial value proposition

This produces something substantially more useful than generic AI fact checking.

The system converts customer knowledge into an **auditable, reusable data layer**.

That means the customer is not merely buying generated prose. They are accumulating a structured body of verified, attributable evidence that can support:

- books;
- reports;
- websites;
- press releases;
- annual reports;
- destination guides;
- marketing copy;
- investor materials;
- future AI-assisted writing.

The durable asset is the evidence and provenance layer underneath the writing.

## Architectural principle

> **Human-sourced information remains the authority; AI structures, retrieves and verifies it; the pipeline preserves provenance from source ingestion through final submission.**

That turns private research and local knowledge into reusable commercial infrastructure rather than disposable source material.
