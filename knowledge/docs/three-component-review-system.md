# A Three-Component Review and Flagging Architecture

## Purpose

Editorial rules are not one kind of thing. Some are checkable facts (does this document use the Oxford comma consistently?), some are learned patterns best taught by example (what does this operator's house voice sound like?), and some are irreducible judgment calls (does this sentence mean what it's supposed to mean?). Treating all three the same way — as prompts fed to a language model — wastes the reliability of the first kind and the nuance of the second kind, and produces a system that is expensive, slow, and only approximately consistent.

This document maps a three-component architecture that routes each rule to the layer suited to it: **fixed instructions**, **RAG-retrieved patterns**, and **deterministic local scripts**. The goal is a review pipeline that is as reliable as it can be made mechanically, and reserves model judgment for the residue that genuinely requires it.

---

## The three components

### 1. Fixed instructions (always-loaded)

**What belongs here:** rules that must apply to *every* passage, every time, regardless of topic or context — invariants, not patterns. Also: precedence and conflict-resolution rules (which layer wins when two signals disagree), and role/context scaffolding that structures how the other two components' outputs get interpreted.

**Why it's a separate layer from RAG:** anything retrieval-dependent can fail to retrieve. A rule that must always hold has no business being conditionally surfaced by a similarity search. It should be baked into the instruction stack that loads on every call, the way frontmatter role/context fields already do in the current pipeline.

**Characteristics:**
- Small, stable, rarely edited
- No ambiguity about whether it was "in scope" for a given call
- Versioned like code, not like a knowledge base

**Examples:** flag-not-fix as the operating philosophy; escalation rules (what counts as a failure worth surfacing vs. a low-confidence note); how to weight a script-flag against a RAG-flag when they conflict; global non-negotiables that apply across every operator and client regardless of style profile.

### 2. RAG layer (retrieved, per-operator)

**What belongs here:** patterns that are real but too numerous, too fuzzy, or too example-dependent to write down as explicit rules. This is where "here's what good looks like for this operator" lives — voice, idiom, tone, house style fingerprints, and prior edge cases that a native-speaker reviewer has already resolved once and that are worth surfacing again when something similar recurs.

**Why retrieval instead of a fixed rule:** these patterns don't generalize as logic. "Avoid this phrasing in formal register, except when the client's prior copy has used it deliberately for effect" isn't a rule so much as a family of precedents. A vector store built from an operator's own edited history — the per-operator ChromaDB collections already in place — is a better fit than trying to enumerate every case as a conditional.

**Characteristics:**
- Grows over time as the corpus of edited copy grows (this is the harvesting-into-newsletters idea in another form: reused institutional memory)
- Retrieval is probabilistic — something relevant might not surface for a given passage, and something irrelevant might
- Per-operator isolation gives style customization without cross-contaminating another operator's voice

**Failure mode to design around:** retrieval silently missing a relevant precedent produces no error, just a gap. This is why nothing that must always apply should live only here (see Component 1) — RAG is additive nuance, not a substitute for guaranteed coverage.

### 3. Local deterministic scripts (checkable, no model involved)

**What belongs here:** anything expressible as a test — a regex, a lookup table, a threshold, a structural check. If you can write an assertion for it, it belongs here, not in a prompt of any kind, because a script either passes or throws. There's no ambiguity about whether it ran, and no cost per call beyond compute.

**Characteristics:**
- Deterministic: same input, same output, every time
- Cheap and fast relative to any model call
- Consistent with the "it works or it yells" philosophy — a script's failure is loud and unambiguous by construction

**Two tiers within this component:**
- **Hard checks** — pass/fail, no judgment involved: terminology consistency, banned phrases, citation format, quotation style, number formatting, frontmatter schema validation, structural completeness (required sections present, heading hierarchy intact).
- **Flaggable metrics** — deterministically computed, but the *significance* of the number is a judgment call left to the next layer up: passive-voice frequency, sentence-length outliers, readability scores, same-entity-named-differently detection (fuzzy string matching flags it; deciding which spelling is correct is not the script's job).

---

## How they fit together: pipeline shape

```
                          ┌─────────────────────────┐
                          │   Fixed Instructions     │
                          │  (always loaded, every   │
                          │   call — invariants +    │
                          │   precedence rules)       │
                          └────────────┬─────────────┘
                                       │
   Document  ──▶  ┌────────────────────────────────────────┐
                  │        Local Deterministic Scripts       │
                  │  hard checks (pass/throw) +               │
                  │  flaggable metrics (computed, unscored)   │
                  └────────────────────┬──────────────────────┘
                                       │  (flags + metrics, no judgment attached)
                                       ▼
                  ┌────────────────────────────────────────┐
                  │      RAG Layer (per-operator retrieval)  │
                  │  surfaces relevant style precedent for    │
                  │  each script-flagged passage +             │
                  │  independently scans for pattern-level      │
                  │  issues scripts can't catch                  │
                  └────────────────────┬──────────────────────┘
                                       │  (flags + retrieved precedent, still no final judgment)
                                       ▼
                  ┌────────────────────────────────────────┐
                  │   LLM Call, governed by Fixed Instructions │
                  │  arbitrates: interprets flags + precedent,  │
                  │  resolves conflicts per precedence rules,    │
                  │  decides what's worth surfacing to a human    │
                  └────────────────────┬──────────────────────┘
                                       │  (final flag list, ranked/filtered)
                                       ▼
                  ┌────────────────────────────────────────┐
                  │        Native-speaker reviewer            │
                  │   (phone, ~90 sec/task, small per-task pay)│
                  └────────────────────────────────────────┘
```

**Sequencing logic:**

1. **Scripts run first, always, on everything.** They're cheap, deterministic, and catch what they catch with certainty. Nothing downstream needs to re-check what a script already confirmed or denied.
2. **RAG runs second, scoped by what scripts flagged plus an independent pass for pattern-level issues.** This is where per-operator style judgment enters — not "is this technically wrong" but "does this sound like this operator's copy."
3. **The LLM call sits last, not first.** Its job is arbitration and interpretation — given a script's hard flag and a RAG-retrieved precedent, decide whether this is worth a human's 90 seconds, and if there's a conflict between what a script says and what the retrieved precedent suggests, resolve it per the precedence rules living in fixed instructions. The LLM is never asked to independently notice something a script or RAG layer could have caught mechanically — that would reintroduce the "might silently miss it" failure mode the whole architecture is designed to avoid.
4. **The human reviewer is the final arbiter, not a second-guesser of everything.** They see a short, pre-filtered list of genuine judgment calls, not a raw document — flag-not-fix means their job is corrections on specific flagged spans, not re-reading the whole piece.

---

## Classification framework: routing a new rule

When a new editorial rule is proposed, route it with this test, in order:

1. **Can it be written as a test?** (regex, lookup, threshold, structural check) → **Script.** Stop here.
2. **Must it apply to every passage, unconditionally, with no room for retrieval to miss it?** → **Fixed instruction.** Stop here.
3. **Is it a pattern best taught by example, specific to an operator's voice or a recurring edge case?** → **RAG.**
4. **None of the above — it requires understanding meaning, intent, or nuance in context** → this is irreducible model judgment, exercised at the arbitration step, not pre-encoded anywhere.

A rule that seems to need an LLM on first read is worth running through steps 1–3 before accepting step 4 — the instinct to reach for a model call is usually a sign the rule hasn't been decomposed far enough yet, not a sign it genuinely needs one.

---

## Reliability posture

The architecture inherits its reliability guarantees unevenly across layers, and that unevenness should be explicit rather than papered over:

- **Scripts: full guarantee.** A passing script means the check definitely passed. A thrown error means it definitely failed. No probabilistic gap.
- **Fixed instructions: guarantee of *presence*, not of *correct application*.** The rule is always in context, but whether the model correctly applies it on a given call isn't mechanically enforced. This is the layer most worth periodically auditing against real output.
- **RAG: guarantee of neither.** Retrieval might not surface a relevant precedent, and a surfaced precedent might not actually apply. This layer should be treated as advisory input to the arbitration step, never as a source of hard flags on its own.

This maps directly onto the "it works or it yells" philosophy: the script layer is where that philosophy is cheapest to fully honor, and every rule that migrates from RAG or the LLM layer into the script layer is a rule that becomes genuinely loud-on-failure instead of quietly-approximate.

---

## Practical next step

An audit of the current versioned instruction library, sorted by the four-step classification test above, would likely reveal that a meaningful fraction of what's currently phrased as prose instruction is actually a disguised checkable rule — and moving those into scripts is the highest-leverage, lowest-risk change available, since it doesn't touch the RAG corpus or the reviewer flow at all.
