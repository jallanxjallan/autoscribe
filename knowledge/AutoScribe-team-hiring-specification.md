# AutoScribe Team Hiring Specification

**Date:** 2026-09-05  
**Purpose:** Hiring and evaluation criteria for an agent-first software engineering team responsible for AutoScribe.

---

# 1. Hiring philosophy

AutoScribe will be developed as an **agent-first engineering system**.

Team members are **not expected to write production code manually as their primary mode of work**. Coding agents should perform most implementation work.

The human engineer's role is to:

- understand what the agent produced;
- judge whether it belongs in the architecture;
- identify incorrect assumptions;
- define and preserve invariants;
- review failure modes;
- design meaningful tests;
- detect unnecessary complexity;
- reason about operational behavior;
- accept, reject, or revise agent-produced changes.

The standard is therefore not:

> Can this person type code quickly?

The standard is:

> Can this person understand, direct, review, and safely operate code produced by an agent?

A strong candidate should be able to look at a substantial generated patch and explain:

- what it does;
- why it was implemented that way;
- what state it owns;
- what state it mutates;
- what assumptions it makes;
- where it can fail;
- what could race;
- what could be duplicated;
- what could be lost;
- what should be deleted;
- what tests would prove it safe;
- whether it preserves the architectural contract.

---

# 2. Core expectation: implementation comprehension

Every engineer must be able to read and reason about code in the areas they own.

They need not routinely implement large features from a blank editor.

They **must** be able to:

- follow control flow;
- trace data flow;
- understand interfaces;
- identify side effects;
- reason about error handling;
- understand state transitions;
- identify hidden coupling;
- spot duplicated ownership;
- recognize stale configuration;
- distinguish durable from disposable state;
- identify unsafe retry behavior;
- identify non-idempotent operations;
- identify stale-read and race-condition hazards;
- review tests critically;
- explain production consequences of a change.

An engineer who cannot explain an agent-produced change is not qualified to approve it.

---

# 3. AutoScribe technology stack

AutoScribe is a multi-language system.

The critical implementation layers are:

- **Rust**
- **Python**
- **Node.js / JavaScript**
- **Lua**

No one engineer must be equally expert in all four.

However:

- every engineer should understand the system-level boundaries between them;
- specialists must understand their own layer deeply enough to review agent output reliably;
- senior engineers should be able to reason across language boundaries.

The team should never treat Rust as the "real system" and Python, Node.js, or Lua as incidental glue.

---

# 4. System-level knowledge expected of all engineers

Every engineer working on AutoScribe should understand the following concepts regardless of specialty.

## 4.1 Sources of truth

They must be able to identify which state is authoritative.

Examples include:

- Git state;
- SQLite state;
- Redis state;
- Control repositories;
- generated runtime state;
- local UI state.

They should instinctively ask:

> Is this the source of truth, or merely a cache / index / notification / convenience layer?

## 4.2 Durable versus disposable state

They should understand why:

- durable work must survive crashes;
- attention notifications may be replayed;
- Redis runtime material may be disposable;
- UI receipts must not masquerade as processing state;
- stale caches must not override authoritative repositories.

## 4.3 Idempotency

They must reason correctly about:

- duplicate dispatches;
- duplicate notifications;
- repeated hook execution;
- repeated retries;
- repeated response checks;
- repeated migrations;
- restart recovery.

## 4.4 Failure recovery

Candidates should naturally ask:

- What happens if the process dies here?
- What if the network disappears?
- What if the API call succeeds but acknowledgement fails?
- What if the same work is seen twice?
- What if the user edits the file while this UI is open?
- What survives reboot?
- What gets retried?
- What must never be retried automatically?

## 4.5 Ownership boundaries

They should resist designs where:

- UI layers know service internals;
- services know editor internals;
- configuration is duplicated;
- multiple state stores compete as authoritative sources;
- a convenience layer becomes permanent architecture;
- one implementation layer acquires responsibilities belonging to another.

---

# 5. Product behavior is part of the engineering contract

AutoScribe's alpha-tested behavior should be treated as a production contract.

Engineers are free to change implementation.

They are not free to silently change established behavior.

Candidates should be comfortable working under constraints such as:

- user editorial branches must not be mutated by background services;
- explicit user actions remain explicit;
- failed work remains recoverable;
- retries remain bounded;
- responses are not written over intervening human edits;
- UI state does not substitute for durable service state;
- project vaults remain self-contained;
- Pandoc document interpretation remains outside Rust;
- normal idle operation remains cheap.

---

# 6. Preferred engineering temperament

The preferred AutoScribe engineer is skeptical of unnecessary machinery.

Good instincts include:

- "Why does this exist?"
- "Who consumes this?"
- "Can we delete it?"
- "Why is this configurable?"
- "Is this really durable state?"
- "What happens if this runs twice?"
- "What happens after restart?"
- "Why do we have two implementations of this?"
- "Could the same invariant be enforced with less code?"
- "Does this component know something it should not know?"

Candidates who consistently add abstractions before proving a need are a poor fit.

Candidates who can simplify a system without losing behavior are highly valuable.

---

# 7. Agent-use expectations

All engineers should be comfortable using coding agents as their primary implementation tool.

They should know how to:

- write bounded work orders;
- establish provenance before mutation;
- provide explicit architectural constraints;
- define acceptance criteria;
- restrict permissions appropriately;
- require tests and validation;
- inspect resulting diffs;
- challenge overengineering;
- ask the agent to remove code rather than merely add more;
- recover when an agent follows a locally reasonable but globally wrong path.

A candidate who treats generated code as automatically trustworthy is unsuitable.

A candidate who refuses agentic development on principle is also unsuitable.

The desired mindset is:

> Use the agent aggressively for implementation; use human judgment aggressively for architecture and acceptance.

---

# 8. Role families

The initial team should favor deep generalists with one or two strong specialties rather than narrow implementers.

## 8.1 Systems / Rust engineer

Primary responsibilities:

- service architecture;
- process lifecycle;
- SQLite integration;
- concurrency;
- retry behavior;
- systemd/runtime behavior;
- subprocess boundaries;
- Git/service interaction;
- resource usage;
- production reliability.

Required depth:

- strong Rust comprehension;
- ownership and borrowing;
- concurrency primitives;
- process control;
- error propagation;
- database transactions;
- resource lifetime;
- filesystem safety.

Not required:

- manually writing large amounts of Rust without agent assistance.

Must be able to review generated Rust and explain whether it is safe.

## 8.2 Python / backend workflow engineer

Primary responsibilities may include:

- server orchestration;
- CLI behavior;
- NDJSON pipelines;
- repository operations;
- Control workflows;
- runtime materialization;
- API integration;
- job processing;
- deployment utilities;
- data transformation.

Required depth:

- Python control flow and data models;
- subprocess handling;
- async/sync behavior where relevant;
- filesystem semantics;
- exception handling;
- API clients;
- serialization;
- testability.

Must be able to detect when an apparently harmless Python helper creates hidden state or reliability problems.

## 8.3 Node.js / Obsidian engineer

Primary responsibilities:

- Obsidian integration;
- QuickAdd workflows;
- Dashboard behavior;
- filesystem interaction;
- Git invocation from the UI layer;
- user-state safety;
- plugin configuration;
- migration/update tooling.

Required depth:

- Node.js process model;
- CommonJS/module loading;
- async JavaScript;
- Obsidian plugin/runtime behavior;
- subprocess handling;
- filesystem paths;
- stale UI state;
- renderer blocking;
- configuration ownership.

Must understand that UI convenience state must not become authoritative service state.

## 8.4 Lua / Pandoc engineer

Primary responsibilities:

- document extraction;
- Pandoc filters;
- AST transforms;
- frontmatter/property handling;
- source identity;
- call emission;
- formatting preservation;
- defaults-file behavior.

Required depth:

- Lua;
- Pandoc AST;
- filter lifecycle;
- metadata handling;
- deterministic transformation;
- byte/format preservation concerns;
- interaction between Pandoc defaults and filters.

Must understand the architectural rule:

> Document interpretation belongs in Pandoc/Lua, not in Rust.

## 8.5 Infrastructure / production engineer

Primary responsibilities:

- deployment;
- observability;
- backups;
- service supervision;
- availability;
- recovery;
- resource budgets;
- LLM call budgets;
- capacity;
- incident response;
- security hardening.

The brief is:

> This works. Make it work within hosting and LLM-call budgets, all the time, assuming the person at the other end will routinely do unexpected things.

Required depth:

- Linux;
- systemd/service management;
- networking;
- databases;
- Redis;
- deployment automation;
- logging/metrics;
- backup/restore;
- rate limits;
- quota handling;
- secrets;
- capacity;
- incident diagnosis.

This person should be permitted to challenge implementation choices while preserving behavioral invariants.

---

# 9. Seniority model

Seniority should not be measured primarily by how much code someone can personally produce.

## Junior / developing engineer

Should be able to:

- read generated code;
- explain local behavior;
- run tests;
- identify obvious duplication;
- follow established architecture;
- work from bounded instructions;
- escalate uncertain state or concurrency questions.

Should not independently approve critical architecture changes.

## Mid-level engineer

Should be able to:

- supervise an agent through multi-file changes;
- identify incorrect assumptions;
- design useful tests;
- reason about retries and failure states;
- review interfaces across modules;
- simplify agent-produced implementations;
- own a subsystem.

## Senior engineer

Should be able to:

- review changes across language boundaries;
- detect architectural drift;
- reason about production failure modes;
- challenge unnecessary state and abstractions;
- define invariants;
- design rollback paths;
- distinguish a test that passes from a property that is actually proven;
- review unfamiliar agent-generated implementations quickly and accurately;
- tell an agent to delete hundreds of unnecessary lines rather than polish them.

## Staff / principal engineer

Should be able to:

- reason about the entire system;
- evolve architecture without destabilizing product behavior;
- define operational contracts;
- establish cost and reliability envelopes;
- lead incident analysis;
- make implementation teams interchangeable behind stable boundaries;
- identify when a major rewrite is justified and when it is merely fashionable;
- translate production evidence into architectural change.

---

# 10. Interview process

Traditional whiteboard coding should not be the primary evaluation method.

The interview process should test the work candidates will actually perform.

## Exercise 1 — Review an agent-produced patch

Give the candidate a realistic multi-file patch containing several deliberate issues, for example:

- duplicate state ownership;
- a stale config value;
- an unnecessary new helper;
- unsafe retry behavior;
- a race;
- a synchronous renderer-blocking subprocess;
- a test that proves less than it claims.

Ask:

1. What does this patch do?
2. What concerns you?
3. What would you delete?
4. Which assumptions need verification?
5. What tests are missing?
6. Would you deploy it?

This should be the most important technical interview.

## Exercise 2 — Architecture explanation

Give the candidate a high-level AutoScribe flow.

Ask them to identify:

- sources of truth;
- durable state;
- disposable state;
- retry boundaries;
- user-owned state;
- service-owned state;
- possible failure windows.

Do not ask for syntax.

## Exercise 3 — Agent direction

Give the candidate a deliberately vague engineering request.

Ask them to turn it into a bounded work order for a coding agent.

Evaluate whether they:

- establish provenance;
- define scope;
- preserve invariants;
- avoid unnecessary rewrites;
- require useful validation;
- include rollback;
- distinguish must-have from speculation.

## Exercise 4 — Failure scenario

Example:

> A dispatch was committed. The post-commit hook ran. The machine rebooted two seconds later. After restart the work is not visible in responses.

Ask the candidate to reason through:

- what state should exist;
- what evidence to inspect;
- where loss could occur;
- what must be idempotent;
- what should be retried;
- what should never be guessed.

## Exercise 5 — Production cost review

Give a service trace showing:

- frequent polling;
- repeated API calls;
- Redis churn;
- idle CPU;
- duplicated LLM calls.

Ask the candidate to identify the likely cost risks and propose bounded fixes.

---

# 11. Optional implementation exercise

If a coding exercise is used, the candidate may use an agent.

In fact, agent use should be encouraged.

The exercise should evaluate:

- quality of instructions;
- correctness of review;
- ability to reject bad generated code;
- test quality;
- final explanation;
- architectural judgment.

A candidate who produces a smaller, safer change using an agent should score higher than someone who manually writes more code.

---

# 12. What not to test

Avoid over-weighting:

- memorized syntax;
- obscure language trivia;
- whiteboard algorithms unrelated to AutoScribe;
- ability to implement linked lists from memory;
- framework trivia easily retrieved by an agent;
- coding speed;
- puzzle-solving disconnected from production behavior.

These are weak predictors of success in the intended development model.

---

# 13. Red flags

Strong negative signals include:

- cannot explain generated code;
- trusts tests without examining what they prove;
- treats passing compilation as validation;
- adds new databases/caches/config files casually;
- prefers abstractions before demonstrating repeated need;
- confuses notification with durable state;
- does not consider retries;
- assumes operations happen only once;
- ignores restart behavior;
- treats UI state as authoritative;
- cannot explain rollback;
- wants to rewrite stable components because they dislike the language/style;
- leaves dead compatibility code indefinitely;
- believes generated code does not require review;
- believes agent use removes the need for specialist expertise;
- cannot say "I don't know; I need to verify that."

---

# 14. Strong positive signals

Highly desirable behavior includes:

- quickly identifies unnecessary code;
- asks for the source of truth;
- spots stale references;
- notices duplicated ownership;
- asks what happens after a crash;
- asks what happens if a user clicks twice;
- prefers reversible changes;
- thinks in invariants;
- distinguishes product behavior from implementation;
- uses evidence rather than confidence;
- can explain technical trade-offs in plain language;
- challenges the agent without becoming adversarial to automation;
- reduces a large patch to a smaller one;
- knows when specialist review is required.

---

# 15. Expectations for code review

Approval means:

> I understand this change sufficiently to take responsibility for its behavior.

A reviewer should be prepared to explain:

- purpose;
- inputs;
- outputs;
- side effects;
- error behavior;
- persistent state changes;
- concurrency behavior;
- retry behavior;
- user-state impact;
- operational impact;
- tests;
- rollback.

"No obvious issue" is not sufficient for critical paths.

---

# 16. Team structure

Early AutoScribe hiring should favor a small team of strong reviewers/operators rather than a large team of implementation specialists.

A plausible early structure:

- founder / system architect / product owner;
- systems + Rust/reliability engineer;
- Python/backend engineer;
- Node.js/Obsidian engineer;
- Lua/Pandoc expertise either dedicated or shared by a strong generalist;
- infrastructure/production engineer as commercial deployment approaches.

Some people may cover multiple areas.

The critical requirement is that every major layer has at least one person capable of genuinely reviewing agent output.

---

# 17. Founder relationship to the team

The founder should retain responsibility for:

- product behavior;
- architectural boundaries;
- complexity budget;
- acceptance criteria;
- major source-of-truth decisions;
- user workflow;
- alpha evidence.

Engineers should increasingly own:

- implementation;
- low-level language decisions;
- concurrency mechanics;
- transaction design;
- service deployment;
- monitoring;
- operational tooling;
- incident response.

The founder should be able to say:

> These are the invariants. Change anything underneath them if you can show the result is safer, simpler, cheaper, or more reliable.

---

# 18. Production-team mandate

After alpha testing, the production engineering mandate should be:

> **This works. Your job is to make it work within hosting and LLM-call budgets, all the time, while assuming users will routinely do unexpected things. Preserve the behavior and invariants; change the implementation wherever necessary to achieve reliability, operability, security, and predictable cost.**

That mandate should guide hiring as much as any technology checklist.

---

# 19. Summary hiring standard

The ideal AutoScribe engineer is not primarily a code producer.

They are a **technical reasoner with enough implementation expertise to supervise agents safely**.

They should:

- understand systems;
- understand their specialist language/runtime deeply;
- use agents fluently;
- distrust unnecessary complexity;
- review code critically;
- design for failure;
- preserve behavior;
- understand costs;
- explain their reasoning;
- accept responsibility for what they approve.

The central hiring question is:

> **Can this person make an agent more reliable than the agent would be on its own?**

If the answer is yes, they are potentially valuable to AutoScribe.
