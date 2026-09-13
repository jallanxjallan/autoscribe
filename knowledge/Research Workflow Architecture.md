# Research Workflow Architecture

## Core principle

**Obsidian is the canonical knowledge system.**  
Everything else supports it.

## Research structure

### Content notes
Manuscript or output material.

Content notes should normally link to **whole finding notes**, not to headings or blocks inside larger research files.

Example:

`[[Duane Gingerich's early affiliation remains unresolved]]`

This keeps links durable even when the internal structure of the finding changes.

### Finding notes
The main reusable research unit.

A finding should be **molecular rather than atomically small**: one coherent claim, question, episode, or research problem containing a few closely related facts, observations, contradictions, and citations.

Create a separate finding when:
- the information becomes independently reusable;
- content needs to cite or depend on it;
- several pieces of evidence need to be reasoned about together.

Do **not** create one file for every individual fact.

If a finding grows into several unrelated propositions, split it.

### Topic notes
Research surfaces or MOCs for subjects such as:

`LHGS`  
`Duane Gingerich`  
`Foreign Lawyers in Indonesia`  
`IBRA`

Topics organize and synthesize findings but do not “own” them. A finding may belong to several topics.

Bases can increasingly generate topic views automatically from metadata and links.

## Verification workflow

The normal path should be:

**Content → Finding → Evidence / Source**

When verifying a statement, open the linked finding note and search within that bounded file for the relevant evidence.

There is generally no need for fragile heading- or block-level links.

## Sources

Original papers, PDFs, interviews, archival material, books, web sources, etc. remain evidence.

Important facts and conclusions extracted from them become findings in Obsidian.

## Google Drive

**GDrive sits outside the knowledge architecture.**

Use it for:

- original/source documents;
- collaborative Docs, Sheets and Slides;
- interview material and other shared working files;
- large supporting artifacts;
- exported manuscripts and deliverables;
- review copies and distribution.

Do **not** maintain a second body of research notes in GDrive.

If a Google Drive document contains knowledge worth preserving independently, **promote that knowledge into an Obsidian finding note**. The Drive file remains the evidence or working document.

## System roles

**Obsidian** — knowledge and relationships  
**GDrive** — documents, collaboration and delivery  
**Git** — history and durable state  
**Pandoc / AutoScribe** — transformation and movement between systems

## Governing rule

Keep the **file** as the stable research object.

Headings are internal organization and may change freely. Whole-file links should carry the durable relationships between content, findings and topics.