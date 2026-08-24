# Research Provenance and Verification Design

The core idea is to stop treating research links as brittle structural references and instead treat **facts as persistent, traceable objects** that move through the editorial pipeline with their provenance and verification state attached.

## 1. Human research files stay human-sized

Research notes should remain at whatever granularity is convenient for reading and maintaining. There is no need to create one file per fact or maintain hard links such as:

```text
[[Research Note#Specific Heading]]
```

Those links are fragile because headings move, notes get reorganized, and the filesystem's preferred granularity is not necessarily the right retrieval granularity.

Instead, research notes can carry broad semantic tags:

```yaml
tags:
  - amman
  - financing
  - capex
  - sumbawa
```

The machine creates its own finer-grained retrieval units.

## 2. Build an evidence index automatically

At ingest/index time, split research material into semantic chunks and store something roughly like:

```text
evidence_id
source_file
source_revision
source_hash
start/end location
text
tags
entities
dates
embedding
```

The chunk is a **database object**, not another Obsidian note.

The useful distinction is:

```text
human storage unit      = research note
machine retrieval unit  = evidence chunk
writing unit            = passage / section
```

These should not be forced to coincide.

## 3. Use hybrid retrieval

Vectors should find material by meaning, but should not be the only retrieval mechanism.

A useful query can combine:

```text
vector similarity
+ tag filtering
+ entity matching
+ lexical/BM25 search
+ dates/numbers
```

Vectors are excellent for semantic matching, but exact matching may be better for proper nouns, dates, quoted phrases, and numbers.

Treat the vector database as a **candidate evidence finder**, not a factual authority.

## 4. In-text tags become provenance tokens

A factual assertion can carry a lightweight marker.

Initially:

```text
The fleet expansion was financed with a dollar-denominated term loan.
{fact:F027 status=unverified}
```

Retrieval finds candidate evidence. A verification step reads the evidence in context and, if adequate, changes the state:

```text
{fact:F027 status=verified evidence=EV893}
```

The important point is that **the tag travels with the assertion through subsequent processing**.

It is therefore not merely an annotation. It is pipeline state.

A richer internal record might contain:

```yaml
fact_id: F027
status: verified
evidence:
  - EV893
verified_against_hash: 87ac...
verified_at_revision: abc123
verification_method: source-check
```

The manuscript need not expose all of this. The visible tag can remain compact while the ledger contains the detailed record.

## 5. Verification is not the same as retrieval

This distinction should be hard-coded into the architecture.

```text
retrieval
    ↓
"this evidence might be relevant"

verification
    ↓
"this evidence actually supports this assertion"
```

An embedding similarity score must never automatically produce `verified`.

The verifier should receive:

```text
claim
candidate evidence
source context
source provenance
```

and return something constrained such as:

```text
supported
contradicted
partially-supported
ambiguous
insufficient-evidence
irrelevant
```

Only an accepted verification result changes the fact status.

## 6. Treat factual provenance like taint tracking

The particularly useful idea is to treat verified prose in the same way a compiler or security system treats trusted data.

Suppose:

```text
Production reached 120,000 tonnes in 2024.
{fact:F027 verified}
```

A later editing step changes this to:

```text
Production doubled to 120,000 tonnes in 2024.
{fact:F027 verified}
```

The attached source may prove `120,000 tonnes` but not `doubled`.

Therefore the system should detect that the semantic claim changed and downgrade it:

```text
{fact:F027 status=needs-reverification}
```

This is an important safeguard.

**Verification belongs to the claim, not merely to the tag ID.**

A tag must not allow a substantially rewritten assertion to inherit trust automatically.

## 7. Two separate gates before submission

### Gate A — deterministic status check

No manuscript proceeds while it contains:

```text
unverified
needs-reverification
contradicted
ambiguous
```

The rule is mechanical:

```text
count(non_verified_fact_tags) == 0
```

No LLM judgment determines whether this gate passes.

### Gate B — missing-claim detection

Once all existing markers are verified, run an LLM specifically to find factual assertions that **have no marker at all**.

For example, it may discover:

```text
The company became Indonesia's largest copper exporter in 2019.
```

with no fact object attached.

It creates:

```text
{fact:F119 status=unverified}
```

which kicks the manuscript back into retrieval and verification.

The manuscript advances only when:

```text
all known fact tags verified
AND
LLM finds no material untagged factual claims
```

This second step catches facts introduced accidentally during drafting or editing.

## 8. Provenance should survive all the way to submission

A fact should be traceable through something like:

```text
manuscript claim
    ↓
fact F027
    ↓
verification event
    ↓
evidence EV893
    ↓
source span
    ↓
source revision
    ↓
source hash
    ↓
original research material
```

That lets the system later answer:

> Where did this assertion originate?

and:

> Is the source material still identical to what was checked?

That is the useful blockchain analogy.

## 9. Blockchain-like properties without a blockchain

The relevant ideas are **provenance** and **tamper evidence**, not distributed consensus.

For example:

```text
EV893
source: Materials/Peregrine.md
span: 4182–4629
source_hash: e515...
```

If someone subsequently alters that source text:

```text
new hash ≠ e515...
```

the system knows that the evidence used during verification is no longer identical.

Similarly, a verification event can itself be hashed or committed:

```text
verification_id
fact_hash
evidence_hash
timestamp
pipeline_version
model/version
previous_record_hash
```

You could even hash-chain ledger rows:

```text
record N hash =
hash(record N contents + record N-1 hash)
```

That makes retrospective modification detectable.

There is little reason to deploy an actual blockchain. Git, cryptographic hashes, SQLite/Postgres and an append-only ledger provide the properties needed.

Useful technical descriptions are:

- **content-addressed provenance with an append-only verification ledger**
- **proof-carrying prose**

## 10. Do not confuse provenance with truth

The provenance chain can establish:

> This assertion was checked against this exact source material.

It cannot establish:

> The original source was correct.

Consequently the evidence object should ideally also preserve source quality metadata:

```text
source_type
publisher
publication_date
primary/secondary
authority
confidence
possibly contradictory sources
```

A government annual report, someone's blog and a company press release are not epistemically equivalent even if their hashes are impeccable.

## 11. Important implementation pitfalls

### Tags becoming detached from claims

An editor may move sentences, split paragraphs, join sentences or paraphrase material.

Do not rely merely on character positions.

The fact object needs enough claim identity to determine whether it still belongs to the current assertion.

Potential tools include:

```text
fact ID
claim-text hash
semantic similarity to previously verified claim
AST/span association during Pandoc processing
```

### Verified-tag laundering

Never let:

```text
{fact:F027 verified}
```

remain trusted merely because the literal tag survived an LLM rewrite.

Compare the post-edit claim against the verified claim. Material semantic change → invalidate.

### Vector hallucination

Nearest neighbour does not mean evidence.

The retrieval and verification steps must remain distinct.

### Over-chunking

Tiny chunks destroy context and can make misleading evidence look convincing.

Store a retrieval chunk, but give the verifier surrounding source context.

### Under-chunking

Huge chunks dilute embedding quality and waste context.

Chunk semantically, probably with modest overlap.

### Source mutation

If research files change, previously verified evidence may become stale.

Hash exact source spans or immutable source revisions rather than trusting the current filename.

### Duplicate evidence

The same source may be indexed several ways or copied into multiple notes.

Deduplicate by content hash and source identity where practical.

### Contradictory evidence

Do not merely return the best supporting result. Retrieval should actively look for contradiction where the claim is consequential.

### Numbers

Embeddings are weak at exact numerical provenance. Numbers, dates, proper nouns and quoted phrases deserve strong lexical/exact-match treatment.

### LLM overconfidence

Verification prompts should permit:

```text
insufficient evidence
```

and preferably make that the conservative default.

### Model/version drift

If the system needs serious auditability, record:

```text
verifier
model/version
instruction version
retrieval version
timestamp
```

You probably do not need to reproduce every reasoning step, but you should know **what machinery produced the verification event**.

### Pipeline instructions leaking into prose

Keep these provenance/control objects structurally distinguishable from manuscript content so export can strip them mechanically and so LLMs cannot accidentally interpret them as prose.

## 12. Likely pipeline shape

A future implementation could therefore look approximately like:

```text
Research ingestion
      ↓
chunk + tag + embed + hash
      ↓
Evidence store
      ↓
Draft/passages
      ↓
detect/tag factual claims
      ↓
hybrid retrieval
      ↓
evidence verification
      ↓
fact status update
      ↓
editorial transformations
      ↓
fact-integrity/reverification check
      ↓
deterministic status gate
      ↓
LLM search for unmarked factual claims
      ↓
if found → verification loop
      ↓
submission
      ↓
strip working tags
retain provenance ledger
```

## Architectural principle

> **The manuscript carries verification state, while the evidence store carries provenance. Retrieval discovers evidence; verification establishes support; deterministic pipeline gates enforce the result.**

This lets research files remain loose and human-readable while giving finished prose much stronger traceability than brittle links or a vault full of microscopic notes.
