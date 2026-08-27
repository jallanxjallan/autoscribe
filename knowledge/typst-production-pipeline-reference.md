# Typst Production Pipeline — Reference Recap

## Current decision

For now, the existing **Liquid** and **Wellness** PDFs will be used as-is.

The production pipeline does **not** need to be built immediately. The current prototypes are sufficient as visual/reference material while the wider destination-guide project continues.

When production work resumes, Typst should become the layout engine for the books.

---

## Why Typst

Typst gives much cleaner control over book design than the temporary Pandoc → LaTeX approach used for the prototypes.

It is well suited to:

- A5 book geometry;
- reusable series templates;
- chapter openers and feature pages;
- precise image and SVG placement;
- running heads and folios;
- consistent typography;
- widow/orphan handling;
- no-hyphenation house rules;
- reusable boxes, captions, sidebars and ornaments;
- automated generation of print-ready PDFs.

The design logic should live in Typst rather than in Pandoc filters.

---

## Production model

The eventual production flow should be:

```text
Markdown manuscript
        +
cover / illustrations / captions
        +
book manifest
        ↓
small assembly/build step
        ↓
temporary Typst fragments + resolved asset paths
        ↓
shared destination-guide Typst template
        ↓
typst compile
        ↓
print-ready PDF
```

The important architectural rule is:

> **Typst handles layout. The build step handles paths and assembly.**

Typst should not need to understand the structure of the Obsidian vault or search for source files itself.

---

## Three layers

### 1. Content

The authoritative editorial material remains in Markdown.

Examples:

```text
Chapters/01-opening.md
Chapters/02-arak.md
Chapters/03-tuak.md
Chapters/04-beer.md
```

Captions and other editorial components can remain in the same source system.

These files continue to be edited normally.

### 2. Book definition

Each title has a small manifest describing what belongs in that book and in what order.

For example:

```yaml
title: Indonesia's Liquid Heritage
subtitle: Spirits, wines and beers
edition: August 2026

cover: Assets/liquid-cover.svg

sections:
  - Chapters/01-opening.md
  - Chapters/02-arak.md
  - Chapters/03-tuak.md
  - Chapters/04-beer.md

output: Build/liquid-heritage.pdf
```

The manifest is the authoritative assembly order.

The system should **not** infer book order from filenames, filesystem order, or Typst itself.

### 3. Design

A reusable Typst template controls the visual system for the whole series.

For example:

```text
templates/destination-guide.typ
```

It should contain:

- A5 page size and margins;
- fonts and type scale;
- heading hierarchy;
- chapter openers;
- section styling;
- caption styling;
- image treatment;
- running heads;
- page numbers;
- feature boxes;
- colour palette;
- cover-thumbnail treatment;
- widow/orphan rules;
- no-hyphenation policy;
- POD-safe geometry.

A later designer should be able to change the appearance of the entire series by editing this template without changing manuscript structure.

---

## Role of Pandoc

Pandoc may still be useful, but only as a lightweight manuscript converter.

Its job should be limited to:

```text
Markdown → Typst fragment
```

For example:

```bash
pandoc Chapters/02-arak.md   -f markdown   -t typst   -o .build/liquid/002-arak.typ
```

Pandoc should **not** control page layout or generate the final document structure.

That distinction keeps the system simple:

- Markdown remains the editorial source;
- Pandoc translates markup;
- Typst lays out the book.

---

## Generated Typst driver

The build process can generate a temporary Typst file such as:

```typst
#import "templates/destination-guide.typ": book

#show: book.with(
  title: "Indonesia's Liquid Heritage",
  subtitle: "Spirits, wines and beers",
  cover: "Assets/liquid-cover.svg",
  edition: "August 2026",
)

#include ".build/liquid/001-opening.typ"
#include ".build/liquid/002-arak.typ"
#include ".build/liquid/003-tuak.typ"
#include ".build/liquid/004-beer.typ"
```

This file is machine-generated and disposable.

It is **not** an editorial source file and should never require hand maintenance.

---

## Temporary build directory

All generated files should live somewhere clearly disposable, for example:

```text
.build/
    liquid/
        book.typ
        001-opening.typ
        002-arak.typ
        003-tuak.typ
        004-beer.typ
```

The `.build/` directory can be deleted at any time.

The permanent source of truth remains:

```text
Markdown
+ assets
+ book manifest
+ Typst template
```

This avoids manipulating or flattening source documents just to produce a book.

---

## Eventual build command

The final production experience should be something like:

```bash
book-build liquid.yaml
```

Internally, the build command would:

1. read the manifest;
2. resolve and validate all source and asset paths;
3. preserve the declared section order;
4. convert Markdown sections into temporary Typst fragments;
5. generate the temporary `book.typ`;
6. run `typst compile`;
7. verify that the PDF was produced successfully;
8. place the finished PDF in the print-delivery location.

A sensible destination might be:

```text
delivery/print/
```

---

## Series-level advantage

Liquid and Wellness should eventually use the **same code and same Typst template**.

They should differ primarily in data:

- title;
- subtitle;
- cover SVG;
- accent colour;
- edition/update date;
- ordered section list;
- title-specific content.

This makes a new book mostly a matter of adding a manifest and content, not writing another layout program.

---

## Typography rules established during prototyping

The current prototypes also established several useful house rules for the production template:

- no automatic word hyphenation;
- widow/orphan avoidance should be automatic;
- one-word runts should be discouraged;
- headings should stay attached to the following text;
- small process/feature boxes should move as units rather than split awkwardly;
- layout should be tuned to the target page count rather than repaired manually page by page.

These rules belong in the reusable Typst template, not in individual books.

---

## Practical conclusion

There is no need to build this machinery yet.

The current Liquid and Wellness PDFs can serve as working visual prototypes.

When production begins, the clean architecture is:

> **Markdown for content, YAML for book assembly, Typst for design, and a small build program to connect them.**

That keeps editorial files human-readable, layout reusable, generated files disposable, and the final PDF build suitable for automation.
