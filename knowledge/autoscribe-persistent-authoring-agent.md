---
title: AutoScribe Persistent Authoring Agent
date: 2026-08-13
type: architecture-note
project: AutoScribe
status: proposed
---

# AutoScribe Persistent Authoring Agent

## Central realization

The proposed AutoScribe agent is essentially an automated, productized version of the working relationship developed over the past year: an ongoing conversation in which the model gradually learns the project, recalls previous decisions, helps think through unfamiliar problems, reviews work on request, and turns settled decisions into usable instructions and production actions.

The major commercial value is not simply access to a capable model. It is the persistence of a coherent project across conversations and working sessions.

> Chat history remembers what was said. Project context remembers what remains true.

A user should be able to return after a day, a week, or a month and continue without reconstructing the audience, purpose, terminology, editorial policy, trusted sources, prohibitions, unresolved questions, and current state of the work. On its own, that continuity may justify the subscription price.

## Commercial instruction model

Commercial users will not normally write instruction files. They will begin with presets maintained on the server and adjust them through the interface or through conversation with the agent.

Eventually, the agent will author project-context and other task-specific instructions from its conversations with the user. These instructions will be proposed for review and stored directly in the server database after approval.

The intended division is:

- Server presets provide the stable baseline.
- Project context records what is true throughout a particular project.
- Specific instructions modify behaviour for a task, content class, or plan step.
- Run directives provide temporary instructions for one execution.

The effective instruction set is therefore:

```text
server preset
+ project-context overlay
+ task-specific overlay
+ run directive
```

Instructions do not need to exist as user-side files. Consequently, commercial instruction management requires no user Git repository or Git-style versioning. The database should nevertheless retain internal revisions, provenance, approval state, and audit history.

Presets should remain separately identifiable rather than being silently copied and edited. Project-specific records should overlay them. This makes inheritance comprehensible and prevents a later preset update from erasing project decisions.

## The conversational experience

The agent should provide a direct, continuing exchange with the model. Project setup is only one use of that conversation.

The user might ask:

- What should I research before creating this Materials item?
- Help me define the scope, but exclude prices and timetables.
- Read this chapter and tell me what feels weak.
- Does this contradict anything elsewhere in the project?
- What would a local editor need to verify?
- Compare these two approaches without rewriting either.
- Turn what we have decided into project instructions.

The agent should automatically receive the relevant approved project context, server presets, Materials, outstanding questions, and recent decisions. The user should not have to repeat them.

Behind the conversation, the agent maintains structured project state. The transcript is evidence and history; it is not itself the project context. The agent periodically converts durable conclusions from the conversation into proposed structured records.

## Creating a Materials item through conversation

A conversation may be attached to a project, an existing content item, or a proposed new item. For example, the user could ask for research suggestions for a Materials item about transport across Flores.

The agent could:

1. Clarify the intended readership and scope.
2. Suggest research angles.
3. Separate online research from questions requiring local knowledge.
4. Distinguish durable information from facts likely to expire.
5. Search approved sources or examine uploaded material when requested.
6. Track exclusions such as prices, timetables, or accommodation.
7. Produce a proposed research brief or Materials item.
8. Create the actual item only after explicit approval.

The agent should visibly distinguish among:

- research questions;
- retrieved facts with sources;
- model inferences;
- claims requiring local verification;
- approved project knowledge.

This is particularly important for destination publishing. An online source may establish that a transport route exists while its frequency, booking practice, reliability, and seasonal operation remain matters for a local contributor.

## Agent and pipeline responsibilities

The agent and pipeline should have separate but complementary roles.

| Authoring agent | Pipeline |
| --- | --- |
| Persistent project conversation | Defined production operation |
| Ad hoc and exploratory review | Repeatable processing |
| Holistic editorial judgement | Granular findings |
| Suggestions, diagnosis, comparison | Flags and transformations |
| No plan required | Executes an explicit plan |
| Usually proposes changes | May write approved results at scale |

The agent is the place for questions such as “What is wrong with this chapter?” or “What else should we investigate?” The pipeline is the place for operations such as flagging every unsupported claim, identifying terminology inconsistencies passage by passage, line-editing selected content, or transforming source material into publication-ready prose.

The agent may recommend handing systematic work to the pipeline. It could identify a pattern during an ad hoc review, explain that complete examination requires a granular run, and propose an appropriate plan. Once approved, the pipeline produces exact flags or transformations. The agent can then help the user interpret the results holistically.

> The agent remembers and thinks with the user. The pipeline checks and changes the work at scale.

## Approval boundary

The model should be free to converse, suggest, summarize, critique, and prepare drafts. Persistent or destructive actions require an explicit boundary.

The agent may propose:

- a project-context instruction;
- a task-specific instruction;
- a new Materials item;
- a revision to an existing item;
- a Define Plan configuration;
- a pipeline run.

The client then shows the exact proposal and offers actions such as Approve, Revise, Reject, or Explain. Deterministic server or client code performs the eventual write. The conversational model should not silently rewrite operating instructions or project content.

## Plumbing

The UI should not connect directly to a model provider. The basic path is:

```text
Obsidian or Electron
    -> local Rust service
    -> AutoScribe server
    -> authoring-agent model and approved tools
    -> server database and project resources
```

The Rust service retains its existing role as the local transport and state layer. NDJSON can stream conversational responses so the interaction feels like ordinary chat. The server supplies the appropriate project context and presets, controls model credentials and model selection, exposes narrowly defined tools, records proposals and approvals, and resumes sessions across devices.

The server-side agent needs a small tool set rather than unrestricted database access. Likely operations include:

- read active project context;
- read applicable presets and instruction overlays;
- inspect selected Materials and content;
- search approved research sources;
- create a proposal;
- request approval;
- activate an approved instruction revision;
- request creation or revision of a Materials item;
- propose a plan or pipeline run.

The database would hold projects, guide or authoring sessions, structured project context, instruction records and revisions, proposals, approvals, and conversation summaries. Run records should retain the exact resolved instruction revisions used, ensuring that an old run remains reproducible after the active project instructions change.

## Storage boundary

Different records have different ownership and storage needs:

- **Presets and instructions:** server database only.
- **Conversation summaries and working state:** server database, subject to retention policy.
- **Materials and publication content:** user-owned project content, retaining Git guardrails where appropriate.
- **Research sources and provenance:** attached to the resulting Materials item.
- **Run payloads and results:** stored according to the existing idempotent dispatch and writeback design.

If Materials remain Markdown in the project or shadow tree, approval instructs the Rust service to create or update the local item and commit it. The model does not manipulate Git. If Materials later move to SQLite or another store, the conversational protocol need not change; only the storage adapter changes.

## Relationship with Define Plan

Define Plan should query server presets, approved project context, approved specific instructions, and available engines and scripts. It stores references to instruction identities and revisions rather than paths to instruction files.

The agent may eventually assemble a proposed plan conversationally. The user could discuss the desired outcome, allow the agent to select applicable presets and project overlays, inspect the resulting plan, and approve it. Dispatch then resolves the referenced revisions into the exact payload saved for the run.

Tomorrow's Define Plan work should therefore preserve these constraints:

1. Commercial users do not manually maintain instruction files.
2. Presets and agent-authored instructions live in the database.
3. Project-specific instructions overlay server presets.
4. The interface displays titles, explanations, and effects while identities remain stable database keys.
5. Plans reference exact instruction identities and revisions.
6. The design must leave room for the authoring agent to create and revise project context through conversation.

## Development sequence

A sensible first commercial slice is narrower than a general autonomous agent:

1. Maintain persistent, structured project context across sessions.
2. Hold a project-aware conversation.
3. Review selected material ad hoc without requiring a plan.
4. Turn settled conversational decisions into reviewable project-context proposals.
5. Turn a conversation into an approved Materials item.
6. Recommend and propose pipeline work when systematic processing is warranted.

A demonstrable prototype should be possible in roughly three to five focused working days. A basic version suitable for the developer's own use is likely to require eight to twelve working days. A beta robust enough for Indonesian editors would more realistically require three to five weeks, chiefly because of approval UX, context selection, database revisions, provenance, recovery, and testing rather than the chat interface itself.

## Briefing note: cross-cultural storytelling corpus

An important part of the agent's corpus will be the developer's accumulated advice on how to make a story understandable and compelling across cultural boundaries. This is not merely a house style or a set of rules for producing grammatical international English. It is editorial knowledge about how readers make sense of people, institutions, motives, values, humour, conflict, history, and place when writer and reader do not share the same cultural assumptions.

Much writing fails across cultures even when every sentence is correct. The writer may assume that the significance of an action is self-evident, that an institution needs no explanation, that a local symbol carries the same associations abroad, or that a chronological recital automatically forms a story. Conversely, excessive explanation can flatten the narrative, patronize the reader, or turn culturally specific experience into generic international prose.

The corpus should teach the agent how to recognize and bridge these gaps while preserving the character and authority of the source. Its concerns are likely to include:

- identifying background knowledge that the intended reader cannot safely be assumed to possess;
- explaining institutions, customs, status relationships, and historical references at the moment they become relevant;
- making motives and consequences legible without imposing an alien moral framework;
- preserving culturally specific detail rather than replacing it with generic equivalents;
- distinguishing what requires translation, explanation, analogy, or simply enough narrative context to become clear;
- recognizing where literal translation carries the words but loses the implication;
- retaining unfamiliar names and concepts without overloading the reader;
- finding a narrative line through factual material so that it accumulates meaning rather than reading as a catalogue;
- establishing stakes that are intelligible to outsiders without exaggerating them;
- using concrete scenes, choices, and consequences to carry cultural explanation naturally;
- judging when humour, irony, understatement, formality, or indirection will not travel without help;
- avoiding both exoticism and the erasure of difference;
- separating universal human interest from claims that a particular reaction is culturally universal.

The objective is not to make every story sound Western or to remove the productive difficulty of encountering another culture. It is to give an outside reader enough orientation to understand why the story matters, while allowing its people, setting, and values to remain particular.

### How the corpus should be built

The most valuable material will combine principles with worked editorial evidence. It may include:

- direct advice and observations accumulated through conversations;
- before-and-after passages showing how a cultural gap was bridged;
- explanations of why a revision succeeded or failed;
- recurring diagnostic questions used during review;
- examples from the developer's books and editorial back catalogue;
- counterexamples in which fluent English remained confusing, culturally tone-deaf, or narratively inert;
- distinctions among Indonesian, Chinese, and international readerships where these materially affect the storytelling decision.

Each example should retain provenance and, where possible, a short annotation identifying the editorial problem, the intervention, and the intended effect on the reader. This will make the corpus useful both for retrieval during live work and, later, for evaluation or model adaptation.

In the first version, “training corpus” need not imply fine-tuning a model. The server can retrieve the most relevant principles and examples for the item being discussed and place them in the agent's working context. This approach is cheaper, more transparent, and easier to revise. It also allows the agent to cite or explain the editorial principle behind a recommendation. Fine-tuning can be considered later if the corpus becomes large and stable enough to demonstrate that it improves behaviour consistently.

### How the agent would use it

During an ad hoc review, the agent could identify where a reader from another culture is likely to become confused, misread a motive, miss the importance of a detail, or lose the narrative thread. It could explain the problem without immediately rewriting the text and suggest several ways to bridge the gap.

During Materials development, it could recommend research needed to make a story travel: the local meaning of a gesture, the practical role of an institution, the history behind a dispute, or the reason a place evokes a response that an outsider would not automatically share.

During a pipeline transformation, the same corpus could inform granular flags and controlled revisions across many passages. The pipeline might flag unexplained local references, missing causal links, imported assumptions, or places where explanation has become heavy-handed. More ambitious transformations could make the narrative accessible while preserving factual meaning, voice, and cultural specificity.

This corpus is therefore more than supporting content for the agent. It is a body of editorial intellectual property: a practical method for carrying stories across cultural boundaries. Combined with persistent project knowledge, local contributors, and the production pipeline, it gives AutoScribe something that access to a general-purpose language model alone does not provide.

## Commercial proposition

The strongest initial promise is not “AI pipelines” or even “custom instructions.” It is:

> Continue working without briefing the AI again.

The persistent agent can remember the project, help the user think, conduct or guide research, review work on demand, preserve settled decisions, and apply a developed method of cross-cultural storytelling. The pipeline then provides controlled, repeatable execution across the project.

This is not a speculative departure from the way AutoScribe has been developed. It is the automation and packaging of a collaboration that has already proved useful over approximately a year.
