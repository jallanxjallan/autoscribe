# Yogyakarta History + Contemporary Synthesis Pipeline
### Technical outline — sized for i3 / 8GB NUC

## What this pipeline does differently from corpus dedup

The dedup pipeline removes overlap. This one *combines* two distinct
corpora — settled/published historical-cultural writing, and raw
contemporary notes — into a single narrative, routed through AutoScribe's
existing flag-not-fix, single-origination-step architecture rather than
free-form LLM merging. Hardware constraints are the same NUC, so most of
the resource discipline from the dedup pipeline carries over directly;
this outline focuses on what's specific to the synthesis task.

## Environment

Same isolated venv as the dedup pipeline (this can reuse it — no new
heavy dependencies beyond what's already installed: sentence-transformers,
scikit-learn, anthropic client). No new model needed; same
`all-MiniLM-L6-v2` embedding model applies here.

## Phase 1 — Ingest + stratum tagging

Same streaming extract-to-JSONL approach as the dedup pipeline
(`extracted.jsonl`), but with two tags per chunk instead of one:

- **Topic tag** (heuristic first pass, cheap): kraton/court culture,
  colonial period, batik/craft traditions, Malioboro, food and street
  culture, contemporary arts scene, etc.
- **Stratum tag**: `published` (your finished Java/Bali prose) vs.
  `contemporary_note` (raw, unprocessed).

Stratum matters downstream: published chunks are voice-finished and
should anchor tone; contemporary chunks are raw material that still
needs a pass.

## Phase 2 — Chunk

Published prose chunks by paragraph/section; contemporary notes chunk by
whatever natural unit they already have (note, article). Same
streaming/checkpoint discipline as before — write `chunks.jsonl`.

## Phase 3 — Embed + cluster by topic (not for removal)

Reuse Phases 4–5 of the dedup pipeline almost unchanged — same small
batch size, same SQLite vector storage, same blocked cosine-threshold
clustering to stay off the O(n²) cliff. The difference is intent: here
clustering consolidates rather than flags duplicates. A cluster should
end up holding both a published paragraph on, say, kraton ritual and a
contemporary note about a recent kraton event — same topic, different
stratum, both wanted in the merge.

## Phase 4 — Outline proposal (one LLM call, structural only)

Build a per-cluster summary: topic label, stratum mix (e.g. "3 published
chunks, 2 contemporary notes"), a couple of representative excerpts. Send
the full list of cluster summaries in a **single** LLM call — cheap model
is fine here, this is a structuring task, not prose generation. Ask for
JSON:

```json
{
  "sections": [
    {
      "title": "The Kraton: Ritual and Present-Day Rhythm",
      "cluster_ids": ["c04", "c11"],
      "rationale": "..."
    }
  ]
}
```

Render this as a markdown checklist. This is a review artifact, not a
final decision — reorder, merge, split, or drop sections by hand before
anything moves to generation. Low resource cost either way: one API
call, no local compute.

## Phase 5 — Contradiction/staleness flagging (per section, before generation)

For each finalized section, one cheap LLM call compares the
`contemporary_note` chunks against the `published` chunks in that
cluster and flags factual drift — a closed shop, a changed practice, a
superseded claim. Output is a flag with both source spans, never an
auto-correction. This runs section-by-section after the outline is
locked, so you're not flagging clusters that get dropped or merged away
in Phase 4.

## Phase 6 — Single origination pass (the one generative step)

Per your existing AutoScribe philosophy: generation happens exactly once
per unit, here once per outline section. One LLM call per section, given:

- the section's published-stratum chunks (voice anchor),
- the section's contemporary-stratum chunks (updated texture),
- the Phase 5 flags for that section (so the model knows what's
  contested and can note it rather than silently picking a side).

Output: a draft passage. This is the only phase in the whole pipeline
that writes new prose — everything before it structures and flags,
everything after it edits.

## Phase 7 — Downstream passes (reuse what already exists)

No new build here — route the drafted passages through your existing
AutoScribe steps unchanged:

- AI-trope flagging instruction file (flag-not-fix, `{{ai:CATEGORY|...}}`
  spans).
- Fact-check pass.
- Copyedit pass.
- Optional native-reviewer handoff for any flagged spans.

## Phase 8 — Assembly into passage architecture

Each finished section becomes an atomic `pss__` passage file with an
immutable slug, matching your existing two-tier passage/claim vault
structure — titles and ordering stay editable right up to compile, same
as the HHP workflow.

## Resource notes specific to this pipeline

| Phase | New resource cost vs. dedup pipeline |
|---|---|
| 1–3 Ingest/chunk/embed/cluster | None — identical profile |
| 4 Outline proposal | One extra LLM call, negligible |
| 5 Contradiction flagging | One LLM call per *section* (not per cluster) — fewer than the dedup pipeline's per-cluster triage, since sections consolidate clusters |
| 6 Origination | One LLM call per section — the only generation step, kept deliberately small in count |
| 7–8 | No new local compute — reuses AutoScribe's existing pipeline steps |

Net effect: this pipeline is *lighter* on the NUC than the dedup
pipeline, since it reuses the same embedding/clustering machinery but
makes far fewer LLM calls (once per section rather than once per
cluster), and the actual writing happens inside AutoScribe's existing
infrastructure rather than as new local compute.
