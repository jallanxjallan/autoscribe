# Web, Print and Social Publishing Architecture

## Decision

Use a single canonical content source, with separate build commands for each output platform.

For new high-churn sites such as the destination-guides project, use **Hugo rather than Nikola**. Keep existing Nikola sites if they are stable and there is no practical reason to migrate them.

For social media, use **Buffer as the publishing adapter** rather than maintaining direct integrations with each social platform.

## Core Principle

The renderer must not own the content.

Canonical Markdown and metadata stay in the working content system. Each renderer receives a disposable, target-specific build tree or payload.

```text
                    CANONICAL CONTENT
                     Studio / Markdown
                           │
                  resolve + select files
                           │
           ┌───────────────┼────────────────┐
           │               │                │
           ▼               ▼                ▼
      build-site       build-book       build-social
           │               │                │
           ▼               ▼                ▼
         Hugo            Typst          social records
           │               │                │
           ▼               ▼                ▼
     static website       PDF/POD           Buffer
                                                │
                             ┌──────────────────┼──────────────────┐
                             ▼                  ▼                  ▼
                         Instagram          Facebook           LinkedIn
                         etc.
```

## Why Hugo Instead of Nikola

Nikola was originally attractive because it was Python-based. That advantage no longer matters if the build pipeline is being generated and maintained with AI assistance rather than hand-coded.

Hugo is preferable for a new, frequently changing destination-guides site because it is:

- a single executable rather than a Python environment;
- extremely fast at rebuilding large static sites;
- actively maintained;
- widely used, with a large ecosystem;
- straightforward to deploy as static output;
- well suited to a disposable build-tree model.

Nikola does not need to be removed from an existing stable site merely for consistency. Migration should be driven by a practical need, not by architecture alone.

## Renderer-Specific Build Commands

Keep separate commands for each output target.

Examples:

```bash
build-site destination-guides
build-book liquid-heritage
build-book wellness-heritage
build-social yogya-launch
```

Each command can share common file-resolution and metadata code, but renderer-specific behavior remains isolated.

### Website

```text
select web content
      ↓
materialize Hugo project tree
      ↓
hugo
      ↓
public/
      ↓
deploy
```

### Books

```text
select ordered book components
      ↓
materialize Typst project tree
      ↓
template + file list + content
      ↓
typst compile
      ↓
PDF
```

### Social Media

```text
select source material
      ↓
generate platform-specific variants
      ↓
human review
      ↓
approved social records
      ↓
Buffer
      ↓
platform queues
```

A later `build-all` command can simply call the individual builders. It should not contain separate publishing logic of its own.

## Build Trees, Not Symlink Farms

Do not make symlinks the production architecture merely because Nikola and Typst both expect files within a project root.

Keep one canonical source file and create disposable renderer-specific build trees.

```text
Studio/
├── Content/
│   ├── jamu.md
│   ├── arak-history.md
│   └── ...
└── builds/
    ├── website/
    │   └── hugo/
    └── books/
        ├── liquid-heritage/
        └── wellness-heritage/
```

Duplication inside `builds/` is build output, not duplicate authorship.

This also permits renderer-specific transformations without contaminating the canonical source. The same passage may require different metadata, links, image handling or markup for web, print and social output.

## Social Media Automation

The simplest architecture is to use Buffer as an intermediary.

Autoscribe or another local build process should not maintain integrations with Meta, LinkedIn, X and other networks individually.

Instead:

```text
approved social post
        ↓
publish-social
        ↓
Buffer API
        ↓
platform-specific queue
```

Buffer can handle scheduling and platform authentication. The local system only needs to understand one publishing API.

Where supported, posts can simply be added to a predefined queue rather than calculating individual posting times.

## Human Approval Boundary

Social generation and social publication should remain separate operations.

Recommended workflow:

```text
build-social
     ↓
review
     ↓
publish-social
```

Do not have the generation step publish directly.

This preserves a deliberate human approval boundary before public communication while still automating nearly everything else.

## Social Posts as Records

Unlike transient web or print build fragments, the final approved social posts should normally be retained as records.

Useful fields include:

- source content or source passage;
- platform;
- final approved text;
- media used;
- approval status;
- scheduled/published time;
- external post identifier where available.

This creates a durable record of exactly what was published and where it came from.

## Recommended Stack

```text
Canonical Markdown
      │
      ├── Hugo  → static site → Cloudflare
      │
      ├── Typst → PDF/POD
      │
      └── social build → review → Buffer → social platforms
```

The important architectural rule is:

> **One canonical content source, multiple disposable build targets, and one build command per rendering platform.**

Hugo, Typst and Buffer are adapters at the edge of the system. None of them should become the content-management system.

## Current References

- Hugo: https://gohugo.io/
- Typst: https://typst.app/
- Buffer API: https://developers.buffer.com/
- Cloudflare Workers Static Assets: https://developers.cloudflare.com/workers/static-assets/
