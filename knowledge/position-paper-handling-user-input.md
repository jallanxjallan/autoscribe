# Position Paper: Handling the Vagaries of User Input

## A permissive-intake, canonical-processing policy for AutoScribe

### Position

AutoScribe should not require users to prepare manuscripts as production technicians. Users should be allowed to submit ordinary Word documents in whatever form their existing habits, collaborators and legacy material have produced. The client should preserve the original, normalize the submission into a canonical structured representation, resolve what it can safely, and present only genuine ambiguities for human confirmation.

The governing principle is:

> Be permissive at intake, strict internally, and explicit about uncertainty.

Word styles, bookmarks and orderly citation practices should be treated as a rewarded fast path, not an admission requirement. A well-structured document should pass through normalization with little intervention. A poorly structured document should still be usable, but it should incur a pre-flight stage that converts visual and informal conventions into explicit structure.

## The problem is human, not merely technical

Most writers use Word visually rather than semantically. They make a heading by enlarging or bolding a line, indent with tabs and spaces, type cross-references as prose, and paste text carrying styles from other documents. Even users who understand styles will apply them inconsistently, forget the rules, modify supplied templates or collaborate with people who have different practices.

This behaviour is not an exceptional error condition. It is the normal condition of user input. A system whose reliability depends on every contributor consistently applying paragraph styles, bookmarks and metadata will transfer its complexity to the least controllable part of the system.

Training can improve input but cannot make it dependable. Enforcement would also make adoption harder: clients would have to change their working habits before receiving any benefit from the service. The product should instead absorb ordinary disorder at its boundary.

## Preserve the original and establish a normalization boundary

The submitted manuscript must remain unchanged as the authoritative record of what the user supplied. Processing should operate on a derived copy.

At intake, the client should use Pandoc and associated filters to convert the document into a canonical internal form, preferably the Pandoc abstract syntax tree or normalized Markdown with explicit attributes. Every later pipeline component should receive this canonical form rather than interpreting Word formatting independently.

The intake sequence should be divided into distinct operations:

1. **Lossless extraction.** Capture text, existing styles, headings, lists, notes, links, tables, metadata and other recoverable structure without attempting to improve it.
2. **Deterministic normalization.** Correct conditions with one objectively safe interpretation: repeated spaces, rogue tabs, redundant blank paragraphs, known scene-break conventions, character normalization and established style mappings.
3. **Structural inference.** Interpret ambiguous visual conventions, such as a bold standalone line that probably functions as a heading.
4. **Human resolution.** Present only decisions that cannot be made with sufficient confidence.
5. **Canonical output.** Generate a structured Word document from a controlled reference template, with real paragraph styles, stable identifiers and normalized document objects.

Separating these operations is essential. Mechanical cleanup should not depend on an LLM, while ambiguous semantic decisions should not be disguised as deterministic formatting changes.

## Deterministic rules before model judgment

The system should use the cheapest and most reproducible mechanism capable of making each decision.

Pandoc filters and conventional code should handle:

- whitespace and character sanitation;
- recognized Word-style mappings;
- list and block-quotation normalization;
- empty-paragraph removal;
- known scene-break patterns;
- extraction of hyperlinks, notes and document metadata;
- generation of stable structural identifiers;
- reconstruction through a controlled `reference.docx`.

Models should be reserved for decisions requiring interpretation, including:

- whether a visually prominent line is a heading or ordinary prose;
- the likely hierarchy level of an unstyled heading;
- whether a block is a quotation, caption, sidebar or normal paragraph;
- whether a prose reference points to a particular section;
- whether a manuscript assertion is supported by a particular research passage.

This division makes the pipeline cheaper, auditable and repeatable. It also limits the damage caused by an incorrect model inference.

## Missing information cannot be normalized into existence

Normalization can recover implicit structure, but it cannot recover information the user never expressed. A bold line reading “Background” can plausibly be classified as a heading. The phrase “as discussed earlier” may have several possible targets and cannot safely be converted into a live cross-reference without confirmation.

The system must therefore distinguish among:

- **recognized facts**, where the source representation is explicit;
- **high-confidence inferences**, where one interpretation is materially more likely than the alternatives;
- **ambiguous inferences**, where the user must choose;
- **missing information**, where no defensible inference is available.

Confidence thresholds should govern automation. High-confidence transformations may proceed automatically and be recorded in the run report. Ambiguous and missing cases should enter a review queue. The system should never silently invent structure, sources or cross-reference targets merely to produce a clean document.

## Research material and invisible provenance

Users should be asked to upload the manuscript together with the notes and source material used to prepare it. They should not be required to construct formal bookmarks or expose pipeline metadata in the prose.

The uploaded notes folder supplies an evidence corpus; it does not, by itself, prove which source supports each assertion. During ingest, the system should:

1. record each source file and its immutable revision or hash;
2. divide sources into addressable evidence spans while leaving the human files intact;
3. identify factual assertions in the manuscript;
4. retrieve likely evidence passages for each assertion;
5. attach a persistent, invisible fact identifier to the assertion;
6. store the detailed claim-to-evidence relationship in the database;
7. hash the accepted evidence span so later source changes can be detected.

The manuscript should carry only the identifier needed to preserve the relationship as the assertion moves through editing. Paths, evidence spans, hashes, verification history and confidence belong in the evidence ledger. A material change to the meaning of an assertion should invalidate or downgrade its previous verification.

Optional source hints may improve matching, especially when a user composes inside the client, but imported Word users should not have to understand or maintain them. Hints assist retrieval; only a confirmed claim-to-evidence link establishes provenance.

## The Electron client as the ambiguity boundary

The Electron interface should not expose the internal machinery of document normalization. It should present a concise review list containing only unresolved decisions.

For a structural ambiguity, an item should show:

- the relevant manuscript passage in context;
- the proposed interpretation;
- plausible alternatives;
- the reason confirmation is required;
- simple actions such as **Confirm**, **Choose another**, **Leave unchanged** or **Not structural**.

For an ambiguous source reference, an item should show:

- the factual assertion in manuscript context;
- the most likely supporting passages;
- each source filename and location;
- the reason for ambiguity or a restrained confidence indication;
- actions such as **Confirm**, **Choose another**, **No source** or **Not a factual claim**.

Confirmation should create a durable decision rather than a transient correction. A confirmed heading classification should inform the canonical document; a confirmed source passage should create the fact-to-evidence record. Repeated decisions may later improve project-specific inference, but no learned convention should override an explicit user choice.

The desired user experience is:

> Upload manuscript and notes → review a short ambiguity list → dispatch.

The success measure is not that the system finds many matters to display. It is that deterministic processing and confident inference reduce the list to the smallest set of decisions that genuinely require the user’s knowledge.

## The structured response becomes the future working document

The first run should return a normalized `.docx` generated from the project’s reference template. It should contain real heading and paragraph styles, normalized lists and quotations, stable identifiers, consistent document objects and any resolved internal links.

That returned document should become the recommended basis for subsequent work. This creates a gradual improvement without demanding prior compliance: users may begin with a disorderly legacy manuscript, but after the first pass they possess a structured document that moves efficiently through later runs.

The system therefore creates a one-way ratchet toward order:

1. arbitrary external input;
2. controlled normalization;
3. limited human confirmation;
4. canonical structured response;
5. progressively cleaner subsequent runs.

The original remains available for comparison and recovery. The structured response must not overwrite it automatically.

## Minimum obligations placed on users

The service should impose content obligations only where the intended meaning cannot otherwise be recovered. Users may reasonably be required to:

- identify the manuscript, author and project;
- upload the notes and source material they actually used;
- answer unresolved structural or provenance questions;
- distinguish deliberate separators where visual evidence is inadequate;
- supply missing source material when a claim cannot be supported from the uploaded corpus.

They should not be required to understand Word bookmarks, Pandoc attributes, internal fact identifiers, evidence hashes or pipeline metadata.

## Risks and controls

### False structural inference

A model may convert decorative typography into a heading or assign the wrong hierarchy. The control is confidence-gated inference, preservation of the original and a review queue for uncertain cases.

### Destructive normalization

Whitespace or formatting that appears accidental may be meaningful in poetry, tables, transcripts or other special material. Filters must be aware of block type and project rules rather than applying global substitutions blindly.

### False provenance

Semantic similarity does not prove that a passage was the source of an assertion. Automatic retrieval should propose evidence; verification should record evidence only when the match is sufficiently strong or manually confirmed.

### Review overload

An overcautious system could confront the user with hundreds of minor questions. Review should be prioritized by consequence, group repeated patterns where safe, and suppress matters that do not affect meaning or downstream processing.

### Hidden mutation

Users must be able to distinguish their submission from the normalized result. Preserve the original, produce a separate response document and maintain an auditable transformation record.

### Format dependence

The canonical representation, not Word, should be the pipeline contract. Word is an important intake and response format, but later support for Markdown, spreadsheets or other sources should converge on the same internal structures.

## Product and architectural consequences

This policy places complexity where it can be engineered and tested: inside the client normalization layer and pipeline services, rather than in user behaviour. It also separates product concerns cleanly:

- **Electron** manages intake, local conversion and human confirmation;
- **Pandoc and filters** establish deterministic structure;
- **models** make bounded interpretive judgments;
- **the database** stores provenance, decisions and verification state;
- **the response generator** produces the structured document;
- **the original file** remains the immutable intake record.

The architecture is therefore tolerant at its external boundary but disciplined after ingest. This is not an indulgence toward poor input. It is recognition that user behaviour is variable, legacy material is unavoidable, and production reliability can only be achieved by converting that variability into an explicit, controlled internal form.

## Conclusion

AutoScribe should accept ordinary user documents rather than require pre-existing production discipline. The client should preserve the original, normalize mechanically safe features, infer only what can be inferred responsibly, and ask the user to resolve the remaining ambiguities through a focused Electron review queue. It should then return a canonical structured document that becomes the preferred basis for later runs.

This approach minimizes training, lowers adoption friction and prevents informal Word practices from contaminating downstream processing. At the same time, it avoids the opposite error of pretending that automation can reconstruct information that was never supplied. The proper boundary is neither rigid submission rules nor unrestrained AI guessing, but permissive intake followed by strict normalization and selective human confirmation.
