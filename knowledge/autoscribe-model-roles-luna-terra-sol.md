# Model Roles in the Autoscribe Pipeline

## Working Rule

Use the models according to the kind of judgment required:

> **Luna routes. Terra flags. Sol edits.**

The models should be treated as capability levels, not as three compulsory sequential stages.

## Luna: Classification, Extraction, and Routing

Luna is best suited to high-volume, low-judgment work where the output can be constrained and checked.

Typical uses:

- classify passages, findings, entities, and topics
- extract names, dates, places, claims, and other structured data
- select potentially relevant standing instructions
- interpret vector-search or similarity results
- convert script/model output into compact structured flags
- decide whether a later processing step is needed
- choose or construct the next runtime instruction
- produce JSON/NDJSON or other tightly structured output
- stop a run early when nothing significant was found

Luna should generally avoid prose editing. Its value is in cheaply handling the large number of routine cases that do not require literary judgment.

## Terra: Inspection and Flagging

Terra should be used primarily as a language inspector rather than an editor.

Typical uses:

- spelling and punctuation checks
- obvious grammatical-error detection
- duplicated-word detection
- prose-tic detection
- requirement checking
- suspicious phrasing or inconsistency flags
- contradiction or duplication warnings
- assessment of whether a mechanical correction is required

The default rule should be:

> Make a change only when the existing text is objectively erroneous. Do not improve style, diction, rhythm, clarity, concision, transitions, or sentence structure. If a sentence is grammatical but awkward, leave it unchanged.

For anything beyond a clearly mechanical defect, Terra should preferably return a flag rather than rewrite the prose.

The recent HHP test showed why this boundary matters: Terra's cleanup pass turned human-sounding prose into smoother but generic exposition. Sentence-level correctness was often preserved, but compression, rhythm, emphasis, and authorial character were lost.

## Sol: Editorial Judgment and Writing

Sol should handle any task where the model must make a meaningful editorial choice.

Typical uses:

- line editing
- rewriting
- concision
- transitions
- voice preservation
- tone
- emphasis
- synthesis
- resolving awkward but grammatical prose
- consolidating overlapping passages
- substantive proofreading choices
- deciding how flagged material should actually be revised

For HHP and similar authored material, any stylistic intervention should therefore go to Sol.

## Pipeline Consequence

The three models do not need to appear in every run.

Examples:

```text
vector search
→ Luna interprets matches
→ no significant issue
→ stop
```

```text
proofing script
→ Terra assesses mechanical flags
→ objective errors corrected
→ write back
```

```text
similarity check
→ Luna identifies probable overlap
→ Terra confirms that the overlap is substantive
→ Sol receives a focused instruction
→ Sol consolidates while preserving voice
```

This fits the planned dynamic-runtime-key architecture particularly well. A cheap model can inspect the result of a script, vector search, or local-model call and decide whether to append a new instruction to the next runtime step. Sol is then reserved for cases that genuinely need editorial judgment.

## Architectural Principle

The useful distinction is not simply model size. It is the kind of work being delegated:

- **Luna:** structured judgment with a narrow answer space
- **Terra:** defect detection and mechanical language checks
- **Sol:** open-ended editorial judgment and prose generation

This should reduce cost while also protecting authored voice from unnecessary model intervention.
