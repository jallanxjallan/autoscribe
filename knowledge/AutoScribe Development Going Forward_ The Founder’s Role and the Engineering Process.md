# AutoScribe Development Going Forward: The Founder’s Role and the Engineering Process

## Position

AutoScribe has reached the point where its development process should change.

During early development, the central problem was invention: discovering what the system should do, what its components should be, and which abstractions were actually useful. That required rapid iteration, experimentation, frequent architectural change, and a willingness to discard substantial amounts of work.

The emerging problem is different. AutoScribe now has a coherent architecture and increasingly well-defined behavioral contracts. The next stage should therefore move from **building features by implementation intuition** toward **preserving demonstrated behavior through explicit architectural invariants, bounded engineering work, and increasingly rigorous operational validation**.

The founder's best role in that process is not to become the project's senior Rust programmer.

It is to remain the person who understands what the system is for, determines which complexity is justified, defines the boundaries between components, specifies the invariants that implementation must preserve, and decides whether observed behavior is acceptable.

The engineers—human or agentic—should increasingly own implementation.

---

## 1. The founder's comparative advantage is architectural judgment

The most important decisions in AutoScribe have generally not depended on detailed knowledge of a programming language.

They have been questions such as:

- Should state live in Git, SQLite, Redis, or nowhere at all?
- Is an event durable state or merely a notification?
- Does every vault need a database?
- Should a daemon depend on the editor being open?
- Should instructions be materialized or read from their authoritative repository?
- Is another configuration entity actually useful?
- Is a socket protocol necessary when a Git hook already expresses the event?
- What should happen when the same work is submitted twice?
- Which files may a background process modify?
- What should survive a restart?
- Which operation must remain explicitly under user control?
- Is a mechanism solving a real problem, or merely preserving an earlier design?

Those are architectural and product questions.

Detailed Rust expertise would help assess particular implementations, but it would not automatically produce better answers to them.

The founder should therefore resist a natural temptation at this stage: trying to close the perceived expertise gap by becoming sufficiently proficient in every implementation technology to personally review every line.

That would consume substantial time while moving attention away from the area where the founder has the highest leverage.

---

## 2. Implementation literacy is necessary; implementation mastery is not

The founder should nevertheless understand the system deeply.

The appropriate standard is:

> The founder should be able to explain every component's responsibility, every authoritative source of state, every important state transition, and every significant failure mode without needing to explain the internal mechanics of the implementation language.

For example, a dispatch path should be understandable at this level:

```text
User selects source and plan
        ↓
Obsidian records a dispatch in Git
        ↓
post-commit hook gives the dispatcher attention
        ↓
dispatcher records durable retryable work
        ↓
Pandoc extracts calls
        ↓
server executes the plan
        ↓
response service retrieves completed exports
        ↓
user explicitly writes safe responses into editorial Git
```

That description contains almost everything necessary for architectural reasoning.

It does not require knowing how Rust lifetimes, traits, async runtimes, or ownership inference work.

Conversely, if a component cannot be explained at that level, it is probably insufficiently understood regardless of whether its code is technically sophisticated.

---

## 3. Architecture should increasingly be expressed as invariants

Going forward, work orders should emphasize what must remain true rather than prescribing implementation unnecessarily.

Examples of AutoScribe invariants include:

- User editorial branches are never mutated by background services.
- A missed notification cannot permanently lose durable work.
- Replaying attention is safe.
- Duplicate processing cannot silently corrupt state.
- Plans and instructions have clearly identified authoritative sources.
- Redis contains disposable runtime state, not authoritative configuration.
- Project vaults are self-contained after materialization.
- Obsidian does not know how service daemons are implemented.
- Pandoc owns document interpretation; the Rust service does not acquire document-format knowledge.
- Failed response routing never generates a false receipt.
- A stale UI view cannot overwrite an intervening human edit.
- Normal idle operation should be computationally cheap.
- Every background operation has bounded retry behavior.
- A production operator can determine what happened from durable state and logs.

These invariants should form the stable contract.

Implementations underneath them may change considerably.

This becomes increasingly important once professional engineers join the project. A production engineer should be free to replace an implementation that is difficult to operate, inefficient, unsafe, or unnecessarily bespoke.

They should not be free to accidentally destroy the behavioral properties that alpha testing established.

---

## 4. Alpha testing should become the behavioral specification

The next several weeks of real use are particularly valuable.

The purpose is not merely to find bugs.

Alpha operation should identify the actual behavioral contract of the product.

When a workflow repeatedly proves useful and understandable in real work, document that behavior.

When an architectural assumption proves wrong, change it while the system is still inexpensive to change.

When code or configuration repeatedly turns out to have no purpose, delete it.

The appropriate attitude during this phase is deliberately asymmetric:

> It is cheaper to remove speculative complexity now and restore the small fraction later proven necessary than to carry every historical possibility into production.

This is particularly important for AutoScribe because much of the system has evolved rapidly. Old mechanisms can remain in code, configuration, documentation, or migration scripts long after their architectural reason disappeared.

Pruning is therefore not cosmetic cleanup. It is part of specification.

Every deleted mechanism makes the surviving system easier to reason about.

---

## 5. Development should proceed in bounded engineering passes

The current work-order method is worth retaining.

A good engineering pass should normally have:

**A defined starting state.**  
Repository, branch, installed version, relevant runtime state, and known uncommitted work should be established first.

**A bounded objective.**  
For example, “replace IPC signalling with Git attention,” not “clean up the service.”

**Explicit invariants.**  
State what must not regress.

**Read-only provenance before mutation.**  
Especially where multiple recovered copies, installed binaries, user configuration, or old repositories may exist.

**A narrow mutation boundary.**  
Avoid opportunistic refactoring unrelated to the objective.

**Tests aimed at failure behavior.**  
Success paths are rarely where the serious production defects occur.

**A rollback path.**  
Particularly for binaries, configuration, databases, hooks, and migration operations.

**A final diff review.**  
The implementation should explain itself through the resulting change set.

**No automatic commit merely because tests pass.**  
The final commit remains a deliberate boundary.

This style compensates effectively for the founder not personally auditing every implementation detail.

It converts implementation trust into demonstrable properties.

---

## 6. Coding agents should be treated as implementers, not authorities

Coding agents are extraordinarily productive, but they have a characteristic failure mode: they can produce locally coherent solutions to problems that should not exist.

They are therefore most valuable when given strong architectural boundaries.

The founder's recurring questions should remain:

- Why does this exist?
- What state does it own?
- Who consumes this configuration?
- Is this durable state or convenience state?
- Do we already have a mechanism that provides this property?
- What happens when it fails halfway?
- Can this operation safely happen twice?
- What happens after restart?
- Why is this abstraction preferable to deleting the feature?
- Does this component know something it should not know?

Agents are very good at answering “how can I implement this?”

The founder should remain responsible for asking “should this exist?”

That distinction is likely to remain valuable even as coding models become substantially more capable.

---

## 7. Human engineering review should change emphasis as production approaches

Professional engineers should eventually review the system, but their assignment should not be “tell us whether you like this code.”

The correct brief is closer to:

> This system has survived extended real-world alpha use. Preserve its observed product behavior and architectural invariants. Make it operate continuously, safely, observably, and within defined hosting and LLM-call budgets, assuming users will routinely do unexpected things.

That gives production engineers the freedom they need.

They should be encouraged to challenge:

- process topology;
- deployment mechanism;
- packaging;
- database configuration;
- logging;
- monitoring;
- rate limiting;
- queueing;
- concurrency implementation;
- recovery procedure;
- security boundaries;
- deployment automation;
- resource consumption;
- use of particular libraries or even languages.

They should not casually change user-visible semantics that have already been validated.

The alpha implementation is not sacred.

The product contract increasingly is.

---

## 8. Reliability should be designed for ignorance, not merely hostility

Many systems are designed around malicious attackers while giving inadequate attention to ordinary misuse.

AutoScribe needs both security and misuse tolerance, but its most frequent adversary will probably be a normal user who does something unexpected.

Examples include:

- dispatching twice;
- clicking the same operation repeatedly;
- editing a file while a response is waiting;
- closing Obsidian halfway through an operation;
- rebooting the machine;
- losing connectivity;
- moving or renaming files;
- restoring an old vault;
- changing branches;
- exceeding API quotas;
- submitting malformed documents;
- allowing disks to fill;
- running out-of-date client code against newer infrastructure;
- misunderstanding what a button does.

The default result should be one of three things:

1. the operation succeeds;
2. the operation safely retries;
3. the operation stops with a clear recoverable error.

Silent loss, hidden duplication, state corruption, and destructive guesses should be exceptional.

This should become a central production requirement.

---

## 9. Cost is an architectural constraint, not a later optimization

AutoScribe has two important cost classes:

- infrastructure cost;
- LLM-call cost.

Both should eventually have explicit budgets.

The production team should be able to answer:

- cost per active user;
- cost per processed document;
- cost per plan execution;
- idle infrastructure cost;
- expected Redis/database/storage growth;
- typical and worst-case LLM call count;
- retry amplification during upstream failure;
- cost of pathological user behavior.

The objective is not simply cheapness.

It is **predictability**.

A system whose normal call costs are slightly higher but tightly bounded may be commercially safer than a nominally cheaper architecture whose retries can multiply silently.

The founder's role should be to establish the acceptable economic envelope; engineers should determine how best to remain inside it.

---

## 10. Observability must replace intuition

As the implementation becomes less personally familiar to the founder, production state must become more legible.

For any failed piece of work, an operator should eventually be able to answer:

- What was requested?
- What durable identity did it receive?
- What version of relevant configuration was used?
- Which stage last completed?
- What is currently blocking progress?
- How many attempts have occurred?
- When is the next retry?
- Which LLM calls were made?
- What did they cost?
- Was anything written back?
- Can the operation safely be replayed?

This does not mean building an enormous observability platform during alpha.

It means ensuring the underlying state model permits these questions to be answered.

Later production tooling can expose it.

---

## 11. The founder should retain ownership of product and architectural simplicity

The founder's continuing responsibilities should be concentrated in five areas.

### Product behavior

Determine what users are trying to accomplish and whether the system actually helps them do it.

### Architectural boundaries

Decide which component owns what and prevent accidental erosion of those boundaries.

### Complexity budget

Demand justification for every persistent state store, daemon, protocol, configuration entity, cache, abstraction, and background process.

### Acceptance criteria

Define what observable behavior proves that a piece of work is complete.

### Alpha reality

Use the product intensively enough to detect when an elegant implementation produces an unpleasant workflow.

These responsibilities cannot easily be outsourced because they depend on the history and purpose of the product.

---

## 12. The founder should increasingly relinquish implementation ownership

Conversely, the founder should gradually stop being the person responsible for:

- choosing exact Rust abstractions;
- designing low-level concurrency primitives;
- deciding detailed database transaction boundaries;
- maintaining systemd deployment scripts personally;
- evaluating dependency internals;
- hand-reviewing every generated function;
- diagnosing production incidents from source code alone;
- preserving implementation approaches simply because they are familiar.

Those responsibilities should increasingly move to engineers with appropriate specialties.

The founder should remain capable of asking for an explanation and challenging a result.

That is different from needing to produce the implementation independently.

---

## 13. A useful decision rule

When evaluating whether to learn or personally solve a technical issue, ask:

> Does understanding this change a product or architectural decision I am responsible for?

If yes, learn enough to make that decision confidently.

If no, require the implementer to explain the relevant trade-off and demonstrate the necessary invariant.

For example:

Understanding why dispatch attention must survive restart matters.

Understanding the exact Rust ownership pattern used to implement the SQLite handle probably does not.

Understanding why two simultaneous enqueues must not corrupt the instruction slug map matters.

Being able to write the Redis Lua script personally does not.

This distinction protects the founder's attention.

---

## 14. The transition to production

A sensible path from the current state is:

**Alpha:**  
Continue aggressive simplification and real-world use. Change architecture when evidence justifies it.

**Behavioral freeze:**  
After sustained use, document the workflows and invariants that have proven themselves.

**Technical diligence:**  
Have experienced engineers inspect the implementation, deployment model, security boundaries, resource usage, recovery behavior, and operating costs.

**Production hardening:**  
Allow substantial internal changes provided behavioral compatibility and invariants are preserved.

**Operationalization:**  
Build deployment automation, monitoring, incident tooling, backups, capacity planning, cost controls, and documented recovery procedures.

**Commercial scaling:**  
Only then optimize for larger numbers of users, multiple jurisdictions, higher concurrency, and increasingly adversarial environments.

The mistake would be attempting to production-engineer every alpha mechanism before proving that the mechanism deserves to survive.

---

## Conclusion

The founder's role in AutoScribe should evolve rather than diminish.

Early on, ownership meant personally driving nearly every implementation decision.

Going forward, ownership should increasingly mean defining the system clearly enough that other people can safely change its implementation.

The objective is not to become the person who knows the most Rust.

It is to become the person who can say:

> This is what the system does. These are the properties it must preserve. These are the costs we can tolerate. These are the failure modes we consider acceptable. You may change anything underneath those constraints if you can demonstrate that the result is better.

That is the appropriate role for the architect of a system moving from experimental software toward a product.

The strongest evidence of success will eventually be that experienced engineers can take substantial ownership of AutoScribe without requiring the founder to supervise their code—and without losing the simplicity, behavior, and operational discipline established during alpha.