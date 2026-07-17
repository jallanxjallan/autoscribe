# Orchestrator Refactor Reminder

## Objective

Remove the separate per-call index and derive runtime progress directly from the artifacts that share the call identity.

The active-call sorted set remains. Its only jobs are:

- identifying calls that the orchestrator must inspect;
- controlling the order and timing of polling;
- providing the active-call count needed to judge whether an unresolved task is still plausibly inflight or has been swallowed.

It is not an execution-state index.

---

## Runtime key shape

All runtime records for one call use the call identity and, where applicable, the step ordinal:

```text
call:<call_identity>:record

step:<call_identity>:1
task:<call_identity>:1
result:<call_identity>:1
failure:<call_identity>:1

step:<call_identity>:2
task:<call_identity>:2
result:<call_identity>:2
failure:<call_identity>:2
```

A call should normally have no more than roughly ten steps. It is therefore trivial for the orchestrator to construct the possible task keys and search backwards for the highest existing ordinal. No scan or secondary index is needed.

---

## Required runtime fields

Store the following on every runtime record:

```text
call_identity
total_steps
```

Records belonging to an ordinal also carry:

```text
ordinal
```

The invariant is:

```text
1 <= ordinal <= total_steps
```

Every runtime artifact belonging to the same call must carry the same `total_steps`.

`total_steps` serves two purposes:

1. It gives the orchestrator the upper bound for searching backwards for the latest task.
2. It provides the termination condition: a successful result for a task whose ordinal equals `total_steps` completes the call.

The call record supplies `total_steps` before the first task exists. Later runtime records remain independently intelligible because they also contain it.

---

## Orchestrator polling sequence

For each due call identity taken from the active-call sorted set:

```text
1. Load the call record.
2. Read total_steps.
3. Search backwards from total_steps to 1 for the highest existing task.
4. Inspect the outcome associated with that task.
5. Either create the next task, leave the call inflight, declare failure, or terminate the call.
```

The latest task can be found with a bounded reverse lookup:

```python
latest_task = next(
    (
        task
        for ordinal in range(total_steps, 0, -1)
        if (task := Task.load_optional(call_identity, ordinal)) is not None
    ),
    None,
)
```

At roughly ten steps, this is simpler and clearer than maintaining a call index or stored current-step pointer.

---

## State machine

### No task exists

The call has not yet been dispatched.

```text
create task:<call_identity>:1
enqueue the task
rescore the call in the active zset
```

The orchestrator creates tasks on the fly. Tasks are not pre-materialized at enqueue time.

### Latest task has a result

The dispatched step completed successfully.

If:

```text
latest_task.ordinal < total_steps
```

then:

```text
create task:<call_identity>:<latest ordinal + 1>
enqueue it
rescore the call
```

If:

```text
latest_task.ordinal == total_steps
```

then the call is complete:

```text
remove the call from the active zset
perform any terminal bookkeeping
```

No separate completed flag or call-index update is required.

### Latest task has a failure

Apply the settled failure policy and terminate or retry as appropriate.

The failure artifact is the authoritative outcome. The orchestrator should not maintain a duplicate failure state in a call index.

### Latest task has neither result nor failure

The task is either:

- genuinely inflight; or
- swallowed after dispatch, with no worker outcome produced.

The orchestrator compares the task timestamp with the current time and takes the size of the active-call zset into account.

A task must not be declared lost merely because it is older than one nominal polling interval. The permitted interval must allow for the orchestrator to rotate through all active calls.

Conceptually:

```text
expected revisit interval
    = polling interval × active-call count
```

with an appropriate tolerance or safety margin.

If the unresolved task is still within that interval:

```text
leave the call inflight
rescore it for another poll
```

If the interval has been exceeded:

```text
declare a failed process
create the appropriate failure artifact
apply terminal failure handling
```

The key invariant is:

> An old task with neither a result nor a failure means the dispatched process was swallowed.

The orchestrator must detect this because only it has the polling and active-set context required to distinguish inflight work from lost work.

---

## Task semantics

A task is the orchestrator's immutable dispatch receipt.

The orchestrator must:

```text
create task
then enqueue that task
```

The task timestamp records when dispatch was attempted.

The worker consumes the queue entry and produces exactly one outcome:

```text
result:<call_identity>:<ordinal>
```

or:

```text
failure:<call_identity>:<ordinal>
```

The worker does not update the task. Mutable task status or lease fields should not be needed if swallowed work is detected from:

```text
task creation timestamp
current time
active-call zset size
polling policy
absence of result/failure
```

---

## Role of runtime steps

Runtime steps may remain as immutable resolved execution records:

```text
step:<call_identity>:<ordinal>
```

They can preserve the exact engine, instruction identities, arguments, and other resolved inputs used for that call.

The orchestrator still creates the corresponding task only when that ordinal is ready to run.

The division is:

```text
plan step       reusable definition
runtime step    resolved execution definition for this call
task            dispatch receipt
result/failure  execution outcome
```

The immediate refactor under discussion is removal of the call index, not necessarily removal of runtime step records.

---

## What to remove

Remove the separate per-call index and all logic that treats it as the authoritative account of progression.

Remove or avoid:

```text
stored current ordinal
index-slot mutation after each step
duplicate completed/failed state in the call index
pre-created tasks for every plan step
Redis scans to discover runtime progression
```

Progress is derived from predictable keys and the latest task ordinal.

---

## What remains

Keep:

```text
state:active_calls.index
```

This remains the orchestrator's polling schedule.

Keep the call record as the root runtime record.

Keep immutable tasks and outcome artifacts.

Keep the plan or runtime-step data needed to construct each task on demand.

---

## Core doctrine

```text
The active zset says which call to inspect and when.

The highest task ordinal says which step was most recently dispatched.

The result or failure for that task says what happened.

The task timestamp, current time, and active-call count distinguish inflight work from swallowed work.

total_steps supplies both the reverse-search bound and the completion condition.
```

No separate call index is required.
