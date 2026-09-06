# AutoScribe Deterministic End-to-End Dispatch Audit

## Objective

Audit one complete real AutoScribe dispatch from the HHP vault through the client, Git, service, Control repository, enqueue, Redis, and downstream runtime boundary.

The purpose is to establish **exactly what happens to the dispatch and its data at every boundary**.

Do not infer, speculate, normalize around errors, or add compatibility code.

I will queue a dispatch record in the HHP vault before you begin. Use that specific dispatch as the audit subject.

I will provide additional permissions as required during the work.

## Primary requirement

For the selected dispatch, account deterministically for:

1. what exists on disk;
2. what exists in Git;
3. what the client reads;
4. what the client sends;
5. what the service receives;
6. what Control revision is selected;
7. what exact files are read from that revision;
8. what exact Python objects/dictionaries are constructed;
9. what is passed into `Plan.from_record()`;
10. what is passed into the `Plan` constructor;
11. what enqueue writes to Redis;
12. what runtime state is created;
13. where the run succeeds or fails.

At each boundary, inspect the actual state. Do not reconstruct it from what the code appears intended to do.

## Rules

- Do not make a speculative repair.
- Do not add legacy-plan handling.
- Do not add compatibility parsing.
- Do not add defensive normalization merely to make the run continue.
- Do not change the plan files to accommodate runtime code.
- Do not change Control content unless the audit proves the Control content itself is wrong.
- Do not run broad test suites.
- Do not audit unrelated packages.
- Do not refactor while investigating.
- Do not assume a field came from a source file merely because it exists later in memory.
- Do not assume the current working-tree code is the code actually executed by a daemon or service.
- Do not assume the Control working tree is the revision enqueue actually reads.
- Do not assume Redis state belongs to this run merely because it is recent.

Every important claim in the final report must be backed by an observed value from this run.

## 1. Establish the audit identity

Locate the dispatch I have queued in the HHP vault:

`~/Work/Studio/HHPLawFirm`

Record enough immutable identifying information to follow that one dispatch through the system.

Capture at minimum:

- source file;
- source slug/identity;
- selected plan identity;
- dispatch commit;
- dispatch branch/ref;
- dispatch timestamp if present;
- any client-side dispatch identity;
- any server/process/run identity subsequently assigned.

Do not use a second dispatch during the audit.

## 2. Record initial system state

Before causing the dispatch to progress, capture the relevant initial state.

Check:

- HHP repository status;
- HHP relevant refs and commits;
- currently installed/running AutoScribe service and daemon processes;
- actual executable paths used by those processes;
- relevant environment/configuration;
- client SQLite state relating to this dispatch;
- Redis keys relating to dispatch/enqueue/runtime/failure state;
- operational Control repository HEAD/refs;
- Control revision that would currently be selected.

Where a service is already running, establish which executable and code installation it is actually executing.

Do not assume it is using the source tree being inspected.

## 3. Follow the client dispatch

Allow the queued HHP dispatch to enter the normal dispatch machinery.

Observe the real transition.

Determine exactly:

- how the dispatch is discovered;
- which repository/ref/commit is read;
- which source filepath is selected;
- which plan identity is extracted;
- which Pandoc command/defaults/filter inputs are used;
- what payload is produced;
- what is persisted locally;
- what command or protocol sends it onward.

Capture the actual payload at the boundary immediately before it leaves the client.

If practical, use existing logs/state first. Temporary narrowly scoped instrumentation is permitted only when necessary to observe a value that otherwise cannot be observed.

Do not alter the semantics of the run.

## 4. Follow receipt by `asc`

At the receiving boundary, identify the exact payload received for this dispatch.

Compare it field-for-field with the client-side payload.

Record any identity assigned at this point.

Then follow the code path actually taken by this run into enqueue.

Do not merely trace possible code paths statically. Confirm the branch/functions executed by this run.

## 5. Audit Control revision selection

This is a critical boundary.

Establish the exact immutable Git revision used by enqueue for this dispatch.

Record the full commit hash.

Then inspect the plan directly from that exact Git object, not from the Control working tree.

For the selected plan, capture:

- requested plan identity;
- exact repository path;
- raw bytes or JSON read from Git;
- parsed JSON object immediately after `json.loads()` or equivalent.

Also inspect every instruction referenced by the plan from the same relevant revision according to the current architecture.

Confirm their existence only. Do not introduce validation work that enqueue is no longer supposed to perform.

## 6. Trace the plan object exactly

Follow the selected plan from Git read through to `Plan`.

This section must explicitly resolve the current `record_type` problem.

Capture the value at every transformation point:

### A. Raw repository file

Show the exact keys contained in the JSON stored in Git.

### B. Immediately after JSON decoding

Show the exact Python dictionary keys and values relevant to construction.

### C. After every intermediate helper or repository abstraction

If the dictionary is wrapped, enriched, merged, copied, annotated, or reconstructed, capture its keys after each transformation.

### D. Argument passed to `Plan.from_record()`

Capture the exact object passed.

### E. Object immediately before `Plan.__init__()`

Capture the exact keyword set passed to the constructor.

The audit must identify the precise statement at which `record_type` first appears.

Do not say that it "probably", "appears to", or "may" originate somewhere.

Identify:

- file;
- function;
- statement;
- input before the statement;
- output after the statement.

If `record_type` originates before this run reaches `Plan.from_record()`, show exactly where.

If it originates inside `Plan.from_record()`, show exactly where.

## 7. Audit instruction handling

For every instruction referenced by this plan:

- record the identity specified by the plan;
- establish the exact Control path resolved;
- confirm the object exists at the selected revision;
- record what enqueue actually extracts or materializes;
- record any Redis identity/key created.

The current architecture assumes properly authored current-format Control content.

Do not add legacy or malformed-content support.

## 8. Audit Redis state

Capture Redis state for this dispatch before and after each significant server-side transition.

At minimum inspect:

- any enqueue input/state keys;
- instruction materialization keys;
- runtime/process keys;
- response keys if reached;
- failure keys;
- TTLs;
- indexes or lookup structures referring to those keys.

Associate each key with this specific dispatch/process identity rather than listing unrelated Redis state.

For hashes, inspect actual fields and values.

For each newly created key, identify the code path that created it.

## 9. Follow runtime until the first terminal result

Continue the same dispatch until it either:

- successfully reaches the intended runtime/engine boundary; or
- creates a failure.

If it fails, capture:

- exact exception type;
- exact exception message;
- exact location;
- process identity;
- failure identity;
- Redis failure record;
- logs surrounding the failure;
- immediately preceding input/object state.

Do not restart with another dispatch to get a cleaner example. The first run is the audit subject.

## 10. If temporary instrumentation is required

Instrumentation must be surgical.

It may print or log:

- identities;
- immutable Git revisions;
- paths;
- dictionary keys;
- selected field values;
- function boundaries;
- Redis keys.

Do not introduce generalized tracing infrastructure.

Do not change object shapes to make logging easier.

Do not catch exceptions that would otherwise propagate.

Do not repair the run while tracing it.

After the audit, remove temporary instrumentation unless it is clearly useful permanent diagnostics and I explicitly approve retaining it.

## 11. Determine the root cause

Only after the complete run has been traced, state the root cause.

The root-cause statement must have this form:

> The source value was **X** at boundary **A**.  
> Statement **Y** in **file:function** transformed it into **Z**.  
> That value reached **file:function** as **Z**, causing **exception/result R**.

For the current `record_type` failure, explicitly answer:

- Is `record_type` present in the Git plan JSON? Yes or no.
- Is it present immediately after JSON parsing? Yes or no.
- At what exact statement does it first appear?
- Why is that statement adding it?
- Does any current consumer actually require it?
- Is the correct fix at the producer of that transformed record or at `Plan.from_record()`?

Do not propose both alternatives. Determine which boundary owns the mistake.

## 12. Make only the proven minimal repair

Once the causal chain is established, make the smallest correction at the boundary that is demonstrably wrong.

The intended architecture is simple:

- Control contains correctly constructed current-format plans and instructions.
- There are no legacy plans to support.
- Enqueue needs current Control state and availability of referenced components.
- Plan parsing should not contain compatibility machinery for obsolete formats.

Do not make unrelated cleanup changes.

Do not broaden the patch.

## 13. Re-run the same path once

After the repair, use one fresh HHP dispatch and follow the same essential checkpoints far enough to prove that the specific broken boundary now carries the correct value.

Do not run a general test suite.

The proof is the real dispatch.

If another independent failure occurs after the repaired boundary, stop there and report it separately rather than expanding the patch automatically.

## 14. Final report

Return a concise chronological audit.

Include:

### Run identity

The identities and immutable revisions used to follow the run.

### Boundary table

For each significant boundary:

`boundary → observed input → transformation → observed output`

### Control evidence

- exact Control commit;
- exact plan path;
- raw plan key set;
- decoded plan key set.

### `record_type` provenance

The exact point where it first appears.

### Redis evidence

The keys created for this run and what each contains.

### Failure

The exact first terminal failure from the unmodified run.

### Root cause

One deterministic causal explanation.

### Repair

Files and lines changed, and why that exact change owns the problem.

### Verification

Observed state from the fresh post-repair dispatch demonstrating that the broken boundary is corrected.

## Permission boundaries

Proceed autonomously until an operation requires permission you do not currently have.

When permission is required, stop only at that specific boundary and tell me:

- the exact operation required;
- the exact path/service/resource involved;
- why it is necessary for this audit.

I will grant permissions as we go.

Do not substitute assumptions for inaccessible state.