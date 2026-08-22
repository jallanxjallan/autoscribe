# Dynamic Runtime Instructions and Document/Pipeline Boundary

## Decision

Nothing that affects pipeline processing should live in the document body.

The document body is for authored content and human-facing annotations. Pipeline control information must be extracted or represented separately so that ordinary text cannot accidentally alter execution.

## Directives

Directive extraction should remain in the original Pandoc ingestion stage.

Pandoc parses the source document, identifies directives, removes or separates them from ordinary document content, and passes them into the runtime control path. From that point onward, directives are pipeline state rather than document body content.

This preserves a clean boundary:

- **Document body:** authored text and human-facing annotations.
- **Frontmatter:** durable structural and operational metadata.
- **Directives:** explicit processing instructions extracted at ingestion.
- **Runtime state:** execution data that may evolve as the pipeline runs.

## Dynamic Runtime Keys

When local scripts, vector-similarity searches, small local models, and similar components are introduced, runtime keys should not be treated as immutable.

A plan defines the initial execution topology, but the runtime representation must permit a step to add instructions to a succeeding step.

Conceptually:

```text
passage
  ↓
local script / vector search / small model
  ↓
structured response
  ↓
engine wrapper interprets response
  ↓
wrapper creates a runtime instruction when required
  ↓
instruction is appended to the succeeding runtime step
  ↓
next engine receives the augmented instruction set
```

## Responsibility of the Engine Wrapper

A local component should not need authority over the complete pipeline.

Its job is to return a structured result. Examples might include:

- substantial similarity to another passage;
- a possible contradiction;
- a factual assertion that needs verification;
- terminology requiring normalization;
- evidence that a particular editorial instruction should be applied.

The **engine wrapper** interprets that result in the context of the current plan.

If the result warrants action, the wrapper:

1. creates the appropriate runtime instruction;
2. appends it to the instruction list of the relevant succeeding runtime step; and
3. passes the modified runtime state onward.

Thus the local component reports what it found; the wrapper decides how that finding enters the pipeline contract.

## Architectural Principle

The key distinction is:

> **Plan = initial execution topology.**  
> **Runtime state = the plan plus information and instructions discovered during execution.**

The plan therefore remains understandable and reproducible without requiring every possible downstream condition to be known in advance.

The runtime can adapt as new information becomes available.

## Why This Fits the Loom Architecture

This preserves the modular, "Lego" approach.

A pipeline slot may contain a:

- deterministic script;
- vector similarity operation;
- retrieval operation;
- small local model;
- remote LLM; or
- other future processing component.

Each component only needs a stable structured contract with its wrapper. The wrapper translates component-specific output into the common runtime representation.

This avoids hard-wiring every interaction between components while still allowing earlier steps to influence later ones.

## Consequences for Future Implementation

When local processing components are implemented:

- do not encode pipeline-affecting control information in the document body;
- retain directive extraction in the original Pandoc parsing path;
- distinguish immutable/source document data from mutable runtime state;
- make succeeding-step instruction lists dynamically extensible;
- define structured result contracts for local scripts, similarity searches, and models;
- put interpretation and runtime mutation logic in engine wrappers rather than individual components;
- preserve the original authored plan separately from its evolved runtime state where useful for debugging and provenance.

This should be treated as a design constraint when the local-script, retrieval, vector-similarity, and small-model stages are implemented.
