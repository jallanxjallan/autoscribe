# Fact Verification Guidelines
### For editors working in low-documentation environments (Indonesia and similar)

These guidelines exist because most fact-checking training assumes a dense information environment: multiple independent newspapers, searchable archives, named sources who'll go on record. Indonesia — like a lot of the world outside the US/UK/EU media axis — often doesn't have that. A claim can look confirmed when it's really just one thinly-sourced item that's been copied across five sites. The job is to tell the difference between "verified" and "merely repeated."

Flag, don't fix. If a claim can't clear these checks, mark it — don't silently correct, delete, or soften it. Let a human editor decide.

---

## 1. Count independent sources, not repetitions

A claim appearing on five websites is not five confirmations if all five copied from the same original post. Before treating something as established, trace it back:

- Does each source cite where *it* got the claim, or does it just assert it?
- Do the sources share suspiciously identical phrasing? That's a copy chain, not corroboration.
- Is there a single "patient zero" post (a blog, a wiki, a press release) that everything else traces to?

**Flag if:** the claim has only one traceable origin, however many places repeat it.

## 2. Distinguish reported fact from generated fact

AI-generated wiki sites, auto-summarized aggregators, and SEO content farms now produce material that reads exactly like reported fact — confident declarative sentences, footnote-style numbering — without a journalist, editor, or named source behind it. This is a growing share of what search returns, and it's often indistinguishable from real sourcing by tone alone.

Tells that content may be synthetic or unverified rather than reported:
- Suspiciously precise detail where the honest state of knowledge (per better sources) is "unclear" or "disputed"
- No named author, outlet, or byline
- The site's "about" page is vague about methodology or is itself AI-descriptive
- Details resolve too neatly — genuine gaps in a record rarely fill in cleanly from one source when nowhere else has them

**Flag if:** a detail is precise, uncorroborated, and would be surprising for a well-documented case to have missed.

## 3. Weight source types explicitly

Rough hierarchy, high to low trust, for claims about people, places, and events:

1. Primary documents (contracts, registries, court filings, dated official records)
2. Direct, named eyewitness or participant testimony
3. Original journalism from an identifiable outlet with editorial process
4. Institutional/organizational statements (with awareness of self-interest)
5. Secondary aggregation that cites #1–3 traceably
6. Wikis, forums, uncredited blogs, SEO content
7. AI-generated summaries/wikis with no visible sourcing

A single item from tier 1–2 can outweigh a dozen items at tier 5–7.

## 4. Sanity-check geography, chronology, and scale

Cheap, fast checks that catch a lot of bad claims:

- Do the places named actually relate the way the text implies (same municipality vs. merely "nearby" vs. connected only by a trail/road)?
- Do the dates form a coherent timeline (age at the time, sequence of events)?
- Is the scale plausible (population, distance, price, duration)?

This is quick to run and catches a real share of errors — including ones that originate from a writer or model conflating two nearby-sounding names.

## 5. Treat personal/local testimony as a distinct, valuable category

In low-documentation environments, a lot of real information lives in people's memory, not in print — family members, colleagues, local officials, elders. This is often *more* reliable than what's published, precisely because nothing gets published. But it should be tagged differently:

- Personal testimony is single-source by nature — it doesn't need five confirmations to be worth recording, but it should be labeled as testimony, not treated as independently verified fact.
- Note who the source is and their relationship to the claim (direct witness vs. "someone told them").
- Where possible without being intrusive, ask for something checkable attached to the testimony (a date, a name, a place) that could later be cross-referenced.

**Flag distinctly:** personal-testimony claims should carry a different flag than sourced-but-unconfirmed claims, so editors know not to go hunting for corroboration that likely doesn't exist.

## 6. Don't let absence of contradiction pass as confirmation

"I couldn't find anything disputing it" is not the same as "I found it confirmed." In thin-documentation environments this distinction matters more, not less — there may simply be no one publishing in a position to dispute anything.

**Flag if:** the strongest evidence for a claim is that nothing was found against it.

## 7. Escalation categories for the flag-not-fix pass

When a claim doesn't clear verification, tag it with what kind of gap it is, so the human reviewer knows what to do with it:

- `[UNCORROBORATED]` — single source, no independent confirmation found
- `[SYNTHETIC-RISK]` — source is likely AI-generated or unattributed aggregation
- `[GEO-CHRONO-CHECK]` — internal geography/date/scale inconsistency found
- `[TESTIMONY]` — personal/local source, not independently verifiable, record as such
- `[NO-DISPUTE-ONLY]` — absence of contradiction is the only support found

---

*This document is a starting framework, not a finished spec — it should be tightened against real cases as the RAG/reviewer pipeline gets more editorial mileage.*
