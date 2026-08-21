# Corpus Deduplication & Condensation Pipeline
### Technical outline — sized for i3 / 8GB NUC

## Hardware constraints driving every decision below

An i3 with 8GB RAM has no headroom for careless memory use: no GPU, likely
2–4 threads, and RAM shared with the OS and whatever else is running. The
design choices below all trace back to one rule — **never hold the whole
corpus in memory at once**. Every phase reads from disk, writes to disk,
and can be killed and resumed without redoing prior work.

## Environment

Isolated venv, separate from AutoScribe's own dependency tree (see prior
discussion — torch clashes badly with pinned production deps).

```
python3 -m venv .venv
source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install sentence-transformers scikit-learn pdfplumber python-docx \
            pandas numpy tqdm anthropic
```

Embedding model: `all-MiniLM-L6-v2` (~90MB, 384-dim vectors). Do not reach
for a larger model — on this hardware the gain in cluster quality doesn't
offset the RAM and time cost. Set `torch.set_num_threads(4)` explicitly
(or your actual core count) so it doesn't try to oversubscribe.

## Phase 1 — Extract (I/O-bound, run alone)

Walk the tree, extract text per file, write one JSONL record per file to
disk (`extracted.jsonl`): `{path, ext, mtime, folder, doc_type, text}`.

- Run this as its own process, separate from embedding. PDF extraction
  libraries (pdfplumber/pymupdf) and torch both have nontrivial import
  overhead — don't load both into one long-lived process.
- Stream writes: open the output file once, append per document, flush
  periodically. Never accumulate results in a Python list.
- `doc_type` heuristic tagging (chat_export / work_order / recap / code)
  happens here, from filename + folder pattern — cheap, no model needed.
- Checkpoint: write processed paths to a `.done` set file as you go, so a
  crash or interrupt lets you resume without re-extracting.

## Phase 2 — Chunk (CPU-bound, no model, run alone)

Read `extracted.jsonl` as a generator (line by line — never
`json.load()` the whole file), chunk by doc_type:

- Chat exports: split by turn/heading.
- Work orders / recaps: split by markdown heading.
- Code: split per function/class via `ast` (Python) — cheap, in-memory
  per-file only.

Write `chunks.jsonl`. Same streaming/checkpoint discipline as Phase 1.

## Phase 3 — File-level dedup pass first (cheap, big payoff)

Before touching the embedding model, hash whole-file text
(normalized — strip whitespace, lowercase) and group exact/near-exact
matches by hash. This alone likely resolves the `(1)`/`(2)` copies and
straightforward re-exports with zero model cost, and shrinks what Phase 4
has to embed.

## Phase 4 — Embed (the RAM-sensitive phase)

Load the model once. Process `chunks.jsonl` in small batches
(`batch_size=8–16`, not sentence-transformers' default of 32) to keep
peak RAM down — throughput loss is negligible at this corpus size, and
avoiding a swap-thrash is worth far more than saving a few minutes.

```python
model = SentenceTransformer("all-MiniLM-L6-v2")
for batch in read_jsonl_in_batches("chunks.jsonl", batch_size=16):
    vecs = model.encode([c["text"] for c in batch], show_progress_bar=False)
    write_vectors_to_sqlite(batch, vecs)   # not to a growing numpy array
```

Store vectors in **SQLite** (a `vectors` table, id + BLOB), not an
in-memory numpy matrix or a pandas DataFrame — at a few thousand chunks
this is trivial for SQLite and keeps peak RSS flat regardless of corpus
size. Close the model / drop the reference after this phase completes,
before Phase 5 starts.

## Phase 5 — Cluster (avoid O(n²) memory)

This is the step most likely to blow the RAM budget if done carelessly.
Full pairwise distance matrices (`scikit-learn` `AgglomerativeClustering`
with default affinity) are O(n²) in memory — fine for hundreds of items,
risky past a few thousand on 8GB.

- Prefer a threshold-based union-find over cosine similarity, computed in
  blocks (e.g. per doc_type or per file-hash-cluster from Phase 3) rather
  than one global n×n comparison.
- If you do want scikit-learn clustering, cap it to reasonable
  block sizes (a few hundred items per block) rather than running it
  against the full chunk set at once.
- No UMAP/HDBSCAN dimensionality reduction here — not worth the extra
  dependency weight and memory for a corpus this size; plain cosine
  threshold clustering is sufficient.

Output: `clusters.jsonl` — cluster id → member chunk ids.

## Phase 6 — LLM triage (network-bound, not memory-bound)

One Haiku-class API call per cluster, not per chunk. This phase is cheap
on local resources — it's just HTTP calls — so it can run right after
Phase 5 without concern for the RAM budget. Output JSON per cluster:
`{canonical, verdict, reason, merged_summary}`. Write results to
`triage.jsonl` as they arrive, so a rate-limit hiccup mid-run doesn't
cost you prior progress.

## Phase 7 — Manifest + human review

Build the manifest from `triage.jsonl`: keep / merge-and-archive /
supersede / needs-review. Needs-review bucket gets read by you; the rest
executes via a dry-run-first mover script (print planned moves, confirm,
then execute).

## Phase 8 — Reorganize survivors

Second cheap-LLM pass tags each canonical doc with a topic; mover script
rebuilds the folder tree from those tags. Same network-bound, low-RAM
profile as Phase 6.

## Summary of resource discipline

| Phase | Bound by | Peak RAM risk |
|---|---|---|
| 1 Extract | I/O | Low — stream to disk |
| 2 Chunk | CPU | Low — generator-based |
| 3 File hash dedup | CPU | Low |
| 4 Embed | Model + I/O | Moderate — small batches, SQLite storage |
| 5 Cluster | Memory | **Highest risk** — block, don't go global |
| 6 LLM triage | Network | Low — no local model held |
| 7 Manifest | I/O | Low |
| 8 Reorganize | Network | Low |

Run phases as separate script invocations, each reading the prior
phase's JSONL/SQLite output and exiting cleanly — don't chain them in one
long-lived process. This costs a little startup overhead per phase but
means nothing ever accumulates in memory across phases, and any single
phase can be killed and rerun in isolation.
