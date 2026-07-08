# AutoScribe Orchestrator Recap: Slot Ownership and Nonce Guardrail

Date: 2026-06-30

## Context

The previous pipeline shape risked confusing two different concepts:

1. The logical call execution spine.
2. Runtime artifacts produced by worker or scrivener tasks.

A specific correction triggered the redesign discussion:

> `committed:*` keys should never go directly into the call index.

A committed key is an artifact proving that a scrivener task succeeded. It is not itself part of the logical execution spine.

The call index should not contain a mixture of raw call, step, task, response, transform, failure, and committed keys. Instead, it should contain pointers to slot-state records. Those slot records then describe the current state of each position in the call pipeline.

## Core Decision

Use slot ownership as the guardrail.

The orchestrator creates a slot key for each call-index position. A daemon may only access or complete a slot if the orchestrator gave it the exact slot key through the task record.

The worker or scrivener does not derive the slot from the step number. It presents the slot key it was handed.

This makes the slot key a capability token.

## Proposed Slot Key Shape

Readable, call-local slot key:

```text
slot:<call_identity>:<slot_no>-<slot_nonce>
```

Example:

```text
slot:01KWABCDEF1234567890:1-k7p
slot:01KWABCDEF1234567890:2-m8x
slot:01KWABCDEF1234567890:3-z4q
```

Where:

```text
slot_no     = logical call-index position / step number
slot_nonce  = small random anti-stale token
```

A full ULID is probably unnecessary for the slot because the slot already belongs to a specific call and step number. A short random suffix is enough to distinguish one incarnation of a slot from another.

A three-character nonce may be sufficient as a guardrail, though four to six characters costs little and reduces collision anxiety.

## What Is a Nonce?

A nonce is a “number used once.”

In this pipeline, the nonce identifies a particular incarnation of a slot.

Example:

```text
slot:01KWABCDEF1234567890:1-k7p
```

Here `k7p` says:

```text
This is not merely step 1.
This is this particular incarnation of step 1.
```

If an old worker tries to complete:

```text
slot:01KWABCDEF1234567890:1-k7p
```

but the orchestrator has regenerated the slot as:

```text
slot:01KWABCDEF1234567890:1-m8x
```

then the old task should yell instead of corrupting the call index.

AutoScribe translation:

```text
nonce = tiny anti-ghost token
```

## Call Index Shape

The call index contains only slot keys:

```text
call:<call_identity>:index

0 -> slot:<call_identity>:0-a8f
1 -> slot:<call_identity>:1-k7p
2 -> slot:<call_identity>:2-m8x
3 -> slot:<call_identity>:3-z4q
```

The call index is therefore stable and boring. It is the authoritative spine of the call, but the slot records carry state.

## Slot Record Shape

A slot record stores the current state of that index position.

### Initial call slot

```json
{
  "call_identity": "01KWABCDEF1234567890",
  "slot_no": 0,
  "slot_nonce": "a8f",
  "state": "call_received",
  "call_key": "call:01KWABCDEF1234567890:record"
}
```

### Pending step slot

```json
{
  "call_identity": "01KWABCDEF1234567890",
  "slot_no": 1,
  "slot_nonce": "k7p",
  "state": "step_pending",
  "step_key": "step:01KWPLANIDENTITY:1"
}
```

### Inflight task slot

```json
{
  "call_identity": "01KWABCDEF1234567890",
  "slot_no": 1,
  "slot_nonce": "k7p",
  "state": "task_inflight",
  "owner": "worker",
  "task_key": "task:01KWTASKIDENTITY",
  "step_key": "step:01KWPLANIDENTITY:1"
}
```

### Completed worker task slot

```json
{
  "call_identity": "01KWABCDEF1234567890",
  "slot_no": 1,
  "slot_nonce": "k7p",
  "state": "task_done",
  "owner": "worker",
  "task_key": "task:01KWTASKIDENTITY",
  "step_key": "step:01KWPLANIDENTITY:1",
  "artifact_key": "transform:01KWABCDEF1234567890:1",
  "artifact_kind": "transform",
  "status": "success"
}
```

### Completed scrivener task slot

```json
{
  "call_identity": "01KWABCDEF1234567890",
  "slot_no": 0,
  "slot_nonce": "a8f",
  "state": "task_done",
  "owner": "scrivener",
  "task_key": "task:01KWTASKIDENTITY",
  "artifact_key": "committed:01KWTASKIDENTITY",
  "artifact_kind": "committed",
  "status": "success",
  "table_name": "calls"
}
```

Important distinction:

```text
committed:<task_identity>
```

may appear as a field inside a slot record, but it should not be the value stored directly in the call index.

## Ownership Model

Slot ownership is sequential, not concurrent.

The orchestrator ensures that worker and scrivener tasks are handled one at a time. Step `n + 1` only comes into play after step `n` is done and dusted.

Ownership sequence:

```text
enqueue
  creates the call and posts the call key

orchestrator
  creates call index
  creates slot records
  writes slot keys into the call index
  advances current slot to task_inflight
  creates task containing the exact slot_key
  posts task

worker/scrivener
  receives task
  executes task
  writes artifact
  completes the assigned slot using the exact slot_key
  posts slot_key back to orchestrator

orchestrator
  opens slot_key
  reads task_done state
  decides next transition
```

Only the current slot owner may write the current slot.

This is not a multi-writer race. It is delegated sequential ownership.

## Task Model Addition

A task should carry the exact slot key it is authorized to complete.

Example worker task:

```json
{
  "identity": "01KWTASKIDENTITY",
  "package": "worker",
  "action": "execute_step",
  "data_key": "transform:01KWABCDEF1234567890:1",
  "step_key": "step:01KWPLANIDENTITY:1",
  "slot_key": "slot:01KWABCDEF1234567890:1-k7p"
}
```

The daemon does not compute the slot key. It only presents the one it was handed.

## Access Rule

Daemons should access slot state only through the strict content-index/state layer.

Example conceptual call:

```python
state.content_index.complete_slot(
    slot_key=task.slot_key,
    task_key=task_key,
    artifact_key=result_key,
    artifact_kind="transform",
    status="success",
)
```

No daemon should directly fiddle with Redis list/hash contents for call-index mutation.

## Strict Completion Checks

Even though the pipeline is sequential, completion should still assert the slot state.

A valid slot completion requires:

```text
1. supplied slot_key exists
2. slot_key parses correctly
3. slot record exists
4. slot record state == task_inflight
5. slot record task_key matches the completing task
6. call index still points to this exact slot_key at slot_no
```

Then and only then should the slot be overwritten as `task_done`.

This is not defensive fallback logic. It is assertion logic.

If the task is stale, malformed, replayed, or aimed at the wrong slot, the system should yell.

## Why This Helps

The nonce/slot-key guardrail prevents several stupid-state bugs:

```text
wrong worker task cannot complete another slot
stale replay cannot complete a newly regenerated slot
manual queue poke must include the exact slot key
step number alone is not enough authority
old task incarnations yell instead of corrupting the call spine
```

This is especially useful during resets, retries, truncations, rebuilds, manual testing, or daemon replay.

## Simplification Gained

The pipeline gets one uniform completion protocol:

```text
actor completes task
actor writes artifact
actor replaces task_inflight slot with task_done slot
actor posts slot_key to orchestrator
orchestrator decides next transition
```

This removes the asymmetry where:

```text
worker result required orchestrator to patch the index
scrivener committed did not belong in the index
```

Instead, every completed task looks the same to the orchestrator:

```text
slot_key -> slot record -> state == task_done
```

The orchestrator then decides based on explicit slot fields:

```text
state
owner
task_key
artifact_key
artifact_kind
status
step_key
table_name, if relevant
```

## Recommended Invariants

```text
Call index values are always slot keys.
Slot records are the only mutable execution-state records for index positions.
Artifacts never directly replace slot keys in the call index.
A committed key is an artifact, not an index entry.
A daemon may complete only the exact slot_key assigned in its task.
The call index remains the source of truth for whether a slot key is current.
The slot nonce distinguishes one incarnation of a slot from another.
No fallback behavior: valid transitions work; invalid transitions yell.
```

## Concise Design Summary

```text
call index = spine
slot key = capability token
slot record = current state
nonce = anti-stale incarnation marker
artifact key = evidence/output
orchestrator = transition decider
worker/scrivener = delegated slot completer
```

This keeps the pipeline readable, strict, and sequential while avoiding the previous confusion between logical call state and runtime artifacts.
