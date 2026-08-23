# SVG Commission Brief Pipeline for Artist Callout Sheets

**Suggested filename:** `svg-commission-brief-pipeline.md`

## Purpose

This document defines a pipeline stage for generating **commission briefs for human illustrators** as **SVG-based vector markup sheets**, rather than as raster AI images.

The goal is not to replace the artist. The goal is to create a cheap, editable, deterministic, and locally renderable **art-direction artifact** that shows:

- rough line drawing
- composition guidance
- callout arrows
- labels
- placement notes
- stylistic constraints
- reserved text/caption space

This is especially suitable for destination books, editorial illustration, chapter openers, diagrams, maps, object studies, and other artwork that benefits from a clear human handoff.

---

## Core Principle

Use the model to generate **structured vector instructions**, not finished artwork.

In other words:

- **model** = proposes content and markup
- **local deterministic tools** = validate, render, and write to disk
- **human artist** = creates final art

This preserves a clean division of labor:

1. cheap ideation and markup from the model
2. deterministic rendering by the system
3. final aesthetic judgment by the commissioned illustrator

---

## Why SVG Is the Right Medium

For commissioned artwork, the rough brief needs to be:

- **clear**
- **editable**
- **lightweight**
- **cheap to generate**
- **easy to archive**
- **easy to hand off**
- **renderable locally**

SVG is ideal because it supports:

- line drawing
- shapes
- arrows and leader lines
- labels and text notes
- guides and boxes
- predictable rendering
- easy conversion to PNG/PDF

Unlike raster image generation, SVG generation is just text generation. That makes it a much better fit for a deterministic pipeline stage.

---

## Recommended Use Cases

This stage is suitable for:

- cover illustration roughs
- chapter opener illustration briefs
- spot illustration briefs
- map briefs
- infographic sketches
- figure composition sheets
- architecture or artifact callout drawings
- food/drink object studies
- cultural object annotation sheets
- “artist notes” sheets with layout guidance

This stage is **not** intended for finished painterly art, complex figurative rendering, or final production-quality illustration.

---

## Canonical Artifact Model

The **SVG file** should be treated as the canonical visual artifact.

Derived outputs:

- PNG = preview
- PDF = handoff/print convenience

Recommended artifact set per commission:

- human-readable brief
- SVG markup sheet
- rendered preview(s)
- metadata / manifest

---

## Pipeline Overview

```text
editorial need / passage / illustration concept
    ↓
LLM generates structured commission brief + SVG
    ↓
extract and validate response
    ↓
sanitize / normalize SVG
    ↓
write .svg to disk
    ↓
local renderer creates .png and/or .pdf
    ↓
send package to artist / designer
```

---

## Recommended Directory Layout

```text
commissions/
  borobudur-relief-panel/
    brief.md
    borobudur-relief-panel.svg
    borobudur-relief-panel.png
    borobudur-relief-panel.pdf
    meta.json
```

Alternative flatter layout:

```text
assets/
  commissions/
    borobudur-relief-panel.svg
    borobudur-relief-panel.png
    borobudur-relief-panel.pdf
    borobudur-relief-panel.meta.json
    borobudur-relief-panel.brief.md
```

---

## Output Contract

The model should **not** be trusted with filesystem operations, storage paths, or shell behavior.

It should return a structured payload. The engine should own:

- filenames
- directories
- validation
- rendering
- writing to disk
- failure handling

### Recommended Response Schema

```json
{
  "slug": "borobudur-relief-panel-brief",
  "title": "Borobudur Relief Panel Commission Brief",
  "summary": "A vector markup sheet showing the intended crop, key figures, and callouts for relief details.",
  "purpose": "Commission brief for a human illustrator",
  "canvas": {
    "width": 1200,
    "height": 900,
    "units": "px"
  },
  "style_notes": [
    "Monochrome line drawing only.",
    "Use a clean editorial sketch style.",
    "Keep the background simplified.",
    "Leave space at lower right for caption."
  ],
  "content_notes": [
    "Emphasize the main relief figures in the center.",
    "Indicate costume folds but do not over-render detail.",
    "Mark the border motif for later refinement by the artist."
  ],
  "callouts": [
    {
      "id": "1",
      "label": "Main relief figure",
      "note": "Artist should refine facial expression and hand gesture."
    },
    {
      "id": "2",
      "label": "Border ornament",
      "note": "Use as a decorative frame motif in final art."
    },
    {
      "id": "3",
      "label": "Caption area",
      "note": "Reserve clear space for editorial text."
    }
  ],
  "svg": "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1200\" height=\"900\" viewBox=\"0 0 1200 900\">...</svg>"
}
```

---

## Schema Notes

### `slug`
Stable identifier for asset handling. Should be filesystem-safe and kebab-case.

### `title`
Human-readable title for the commission brief.

### `summary`
Short description of what the sheet contains.

### `purpose`
Useful explicit tag to distinguish this from finished artwork or internal diagrams.

### `canvas`
Defines intended output dimensions for the SVG.

Recommended defaults:
- width: `1200`
- height: `900`
- units: `px`

### `style_notes`
Short production notes describing the intended visual treatment.

Examples:
- line drawing only
- no color
- simplified background
- editorial rather than decorative
- human artist will refine

### `content_notes`
Short subject-matter notes that clarify the visual aim.

### `callouts`
Human-readable callout list. These duplicate, in semantic form, what appears visually in the SVG.

### `svg`
The actual vector markup.

---

## House Style for SVG Commission Sheets

To keep results predictable, define a standard visual grammar.

### Visual rules

- monochrome only
- mostly black or dark gray strokes
- no decorative color
- no photorealistic rendering
- minimal or no fills
- simple line weights
- one sans-serif font
- clean arrowheads
- numbered callouts preferred
- reserved space for title and notes

### Recommended fixed elements

1. **Title bar**
   - title
   - slug or ID
   - optional purpose label

2. **Main sketch zone**
   - simple subject drawing
   - composition and scale indication

3. **Callout arrows**
   - clear leader lines
   - avoid visual clutter

4. **Numbered callout circles**
   - 1, 2, 3, etc.
   - correspond to notes list

5. **Notes area**
   - short style and content guidance

6. **Reserved editorial areas**
   - caption box
   - text-safe area
   - optional crop/trim/frame guides

---

## SVG Content Guidelines

The prompt should steer the model toward **simple, robust SVG**.

### Encourage

- `<svg>`
- `<g>`
- `<path>`
- `<line>`
- `<polyline>`
- `<rect>`
- `<circle>`
- `<ellipse>`
- `<text>`

### Discourage

- embedded raster images
- filters
- masks unless essential
- complex clipping
- CSS dependencies
- JavaScript
- external font references
- external asset references

### Preferred characteristics

- valid XML
- explicit `xmlns`
- explicit `viewBox`
- simple coordinate system
- grouped elements
- readable structure
- text labels placed clearly
- minimal dependence on advanced SVG features

---

## Recommended House Prompt

Below is a reusable prompt for the pipeline stage.

### House Prompt: `illustration-brief-svg`

```text
You are generating a commission brief for a human illustrator.

Your task is to produce a structured response containing:
1. a slug
2. a title
3. a short summary
4. style notes
5. content notes
6. a callout list
7. a complete SVG markup sheet

The SVG is not finished art. It is an editorial markup sheet for a commissioned artist.

Requirements:
- Use monochrome line art only.
- Create a clean vector callout sheet.
- Include a simple line drawing showing the intended composition.
- Add arrows or leader lines pointing to important features.
- Include numbered callouts with short labels.
- Include short notes indicating what the artist should emphasize, refine, or preserve.
- Leave space for editorial notes or caption area if relevant.
- Keep the style simple, functional, and legible.
- Do not create painterly, photorealistic, or highly decorative artwork.
- Do not use external assets, JavaScript, or linked resources.
- Use valid SVG with explicit width, height, and viewBox.
- Use only broadly supported SVG elements.
- Keep paths and structure reasonably simple.

Output format:
Return a JSON object with the following keys:
- slug
- title
- summary
- purpose
- canvas
- style_notes
- content_notes
- callouts
- svg

The svg field must contain a complete SVG document as a string.

Context for this commission:
[INSERT PASSAGE / BRIEF / SUBJECT DESCRIPTION HERE]

Additional layout needs:
[INSERT PAGE USE / CAPTION SPACE / COMPOSITION NEEDS HERE]

Additional style constraints:
[INSERT STYLE CONSTRAINTS HERE]
```

---

## Shorter Prompt Template

For routine automated use, a compact version may be enough:

```text
Generate a JSON response for an illustrator commission brief.

Return:
- slug
- title
- summary
- purpose
- canvas {width,height,units}
- style_notes[]
- content_notes[]
- callouts[]
- svg

The svg must be a complete monochrome editorial callout sheet with:
- simple line drawing
- arrows / leader lines
- numbered callouts
- text labels
- notes area
- reserved caption/text area when useful

This is not finished art. It is a vector markup brief for a human illustrator.

Subject:
[SUBJECT]

Usage:
[USAGE]

Constraints:
[CONSTRAINTS]
```

---

## Suggested NDJSON Envelope

If this becomes a formal pipeline stage, the wrapper payload might look like:

```json
{
  "stage": "illustration-brief-svg",
  "job_id": "job-2026-08-22-001",
  "source_slug": "cnt.borobudur-chapter-opener",
  "request": {
    "subject": "Borobudur relief panel chapter opener illustration",
    "usage": "Chapter opener spot illustration",
    "constraints": [
      "Monochrome line drawing",
      "Reserve lower-right caption area",
      "Emphasize central relief figures"
    ]
  }
}
```

And the response payload:

```json
{
  "stage": "illustration-brief-svg",
  "job_id": "job-2026-08-22-001",
  "result": {
    "slug": "borobudur-relief-panel-brief",
    "title": "Borobudur Relief Panel Commission Brief",
    "summary": "Vector markup sheet for chapter opener illustration.",
    "purpose": "Commission brief for a human illustrator",
    "canvas": {
      "width": 1200,
      "height": 900,
      "units": "px"
    },
    "style_notes": [
      "Monochrome line drawing only."
    ],
    "content_notes": [
      "Reserve lower-right caption area."
    ],
    "callouts": [
      {
        "id": "1",
        "label": "Central relief figure",
        "note": "Artist to refine expression and drapery."
      }
    ],
    "svg": "<svg ...>...</svg>"
  }
}
```

---

## Validation Stage

The local system should validate before writing or rendering.

### Validation checks

1. response is valid JSON
2. required fields exist
3. `svg` contains a complete `<svg>` document
4. width/height/viewBox are present
5. no external references
6. no scripts
7. SVG parses as XML
8. file size is within expected limits
9. optionally sanitize unsupported elements

### Failure policy

If validation fails:

- reject write
- record error
- request regeneration or correction
- preserve source response for inspection

---

## Local Rendering Stage

Recommended render flow:

```text
response
  ↓
extract svg string
  ↓
validate / sanitize
  ↓
write .svg
  ↓
render to .png
  ↓
optionally render to .pdf
```

### Suitable tools

- **resvg** — preferred, especially in a Rust-based stack
- `rsvg-convert`
- `inkscape` CLI

### Preferred architecture

If possible, use a Rust-native renderer rather than shelling out. But shelling out is acceptable if the interface is simple and reliable.

---

## Minimal Processing Rules

The pipeline wrapper should own:

- slug normalization
- path construction
- overwrite policy
- audit trail
- render policy
- metadata writing

The model should **not** decide:

- output folder
- shell command
- file extension strategy
- overwrite behavior
- final storage policy

---

## Suggested Metadata File

Store metadata separately for traceability.

Example:

```json
{
  "slug": "borobudur-relief-panel-brief",
  "title": "Borobudur Relief Panel Commission Brief",
  "source_slug": "cnt.borobudur-chapter-opener",
  "stage": "illustration-brief-svg",
  "created_at": "2026-08-22T20:00:00+07:00",
  "rendered_outputs": [
    "borobudur-relief-panel.svg",
    "borobudur-relief-panel.png",
    "borobudur-relief-panel.pdf"
  ],
  "notes": [
    "Canonical source is SVG.",
    "PNG/PDF are derived outputs."
  ]
}
```

---

## Editorial Workflow Recommendation

For each commissioned artwork item:

1. editor identifies the illustration need
2. pipeline generates brief text + SVG markup sheet
3. local renderer creates preview PNG/PDF
4. human reviews the brief
5. artist receives package
6. finished art returns through separate commission workflow

This keeps rough visual planning separate from final artwork production.

---

## Benefits

### Cost benefits
- avoids expensive image-generation calls for roughs
- uses ordinary text generation instead

### Workflow benefits
- editable artifact
- easy iteration
- cleaner artist handoff
- deterministic rendering
- better archiving and diffing than raster

### Architectural benefits
- fits the existing “Lego” / contract-first model
- deterministic local operations remain outside the model
- supports versioning and structured validation

---

## Limitations

This approach works best for:

- line drawings
- simple shape-based briefs
- clear markup sheets

It is less suitable for:

- finished artwork
- rich painterly concepts
- subtle mood studies
- highly expressive illustration styles

That is acceptable, because the purpose here is **commission specification**, not artwork substitution.

---

## Recommended Naming

Possible stage names:

- `illustration-brief-svg`
- `artist-callout-sheet`
- `commission-brief-svg`
- `figure-spec`
- `art-direction-sheet`

**Recommended choice:** `illustration-brief-svg`

It is clear, literal, and easy to understand in the pipeline.

---

## Bottom Line

For commissioned artwork, an SVG-based brief stage is the right tool when the goal is to generate:

- rough line drawing
- labels
- arrows
- composition notes
- editorial guidance

The output should be treated as a **vector markup brief for a human illustrator**, not as final art.

This makes the process:

- cheaper
- cleaner
- more controllable
- more editable
- more compatible with a deterministic local pipeline

It is a very good fit for the broader system principle:

**models generate content; deterministic tools perform operations; humans make final aesthetic judgments.**