Yes. This is cleaner.

The important simplification is that **plan upload becomes the only place where prompts/instructions are resolved into portable content**. Dispatch no longer has to reason about the dependency graph.

The shape I think you are describing:

```text
client
  asc upload plan <plan_slug>
    - loads local plan
    - reads each referenced prompt/instruction/script reference as needed
    - checks dirtyness / freshness
    - emits one complete PlanRecord
      containing:
        plan slug
        plan identity
        step specs
        embedded prompt/instruction content or content refs
        hashes/timestamps for dirty checks

server
  asc control upload-plan
    - stores/updates plan:<identity>
    - maps slug -> plan:<identity>
    - materializes updated instruction records if needed
    - fans out reusable step records:
        step:<plan_identity>:1
        step:<plan_identity>:2
        step:<plan_identity>:3
```

Then dispatch becomes much dumber:

```text
dispatch-run
  - uploads selected content records as NDJSON
  - each content/call record includes:
      record_plan: <plan_slug or resolved plan identity>
  - server resolves plan slug through slugmap
  - call record stores the plan reference
  - orchestrator uses that plan identity to find:
      step:<plan_identity>:<n>
```

That keeps the upload responsibilities nicely separated:

```text
Plan upload:
  "Define and publish the process."

Dispatch upload:
  "Send these content records through that already-published process."

Orchestrator:
  "Resolve call -> plan -> steps, then execute."
```

The server-side materialization rule also feels right:

```text
plan slug -> plan identity
step index number -> step key

step:<plan_identity>:<number>
```

That gives you stable reusable step keys without putting call-specific data into the plan structure.

The call record only needs to carry the plan reference, probably something like:

```json
{
  "kind": "call",
  "identity": "01...",
  "content_key": "content:01...",
  "plan_slug": "plan.step-factory-test",
  "plan_key": "plan:01...",
  "status": "queued"
}
```

Or, if you want the server to be authoritative, the uploaded NDJSON can contain only:

```json
{
  "record_plan": "plan.step-factory-test"
}
```

and the server resolves that to:

```json
{
  "plan_key": "plan:<identity>"
}
```

I would avoid making dispatch upload prompts/instructions entirely. That path will become annoying because dispatch is about **content selection**, while prompt/instruction upload is about **process publication**.

One useful command split might be:

```bash
asc upload plan <plan-slug>
asc upload plans --dirty
asc dispatch-run
```

Where `asc upload plans --dirty` checks all local plan dependencies and uploads only plans whose embedded prompt/instruction/script content has changed.

The resulting rule of thumb:

> A call never carries the process definition. It carries only a reference to a published plan.
> A plan upload carries the process definition and enough embedded dependency content for the server to materialize executable steps.

That should also retire a lot of awkward “upload submodule” complexity. The client side can do dependency bundling once, during plan publication, instead of making every dispatch think about prompts, instructions, plans, and content files at the same time.