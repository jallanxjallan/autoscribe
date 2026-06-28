# Recap: Index-Driven Process Chain Orchestration

## Context

The current daemon smoke tests became hard to reason about because the process chain required manually tracking three daemons, one-shot claims, queue posts, task keys, result keys, outcome/commit signals, and call index slots.

The problem was not only implementation complexity. It was cognitive complexity: if a human operator cannot easily tell what should happen next by inspecting Redis, the orchestration model is too clever.

The new direction is to make the call index the single readable state machine.

## Core idea

The orchestrator should not depend on callback messages from worker or scrivener daemons for normal continuation.

Instead:

1. The enqueuer materializes a call and its steps.
2. The enqueuer creates `call:<identity>:index`.
3. The enqueuer inserts that call index into an active-call sorted set.
4. The orchestrator repeatedly inspects the oldest active call.
5. The orchestrator finds the first unfinished slot in the call index.
6. The orchestrator advances that slot by one obvious move.
7. The orchestrator bumps the zset score to `now` so other active calls get a turn.

This makes the orchestrator an index-driven scheduler rather than an inbox-driven continuation handler.

## Active zset

The active zset contains call indexes:

```text
active:calls
  call:<call_identity>:index  score=<last_touched_at>
```

The orchestrator always selects the oldest score.

Every inspection or state transition bumps the score to `now`.

This prevents the orchestrator from hammering a blocked call and naturally rotates through the active calls.

## Call index as process state

The call index is the whole process state:

```text
call:<call_identity>:index
  0 = call:<call_identity>:record
  1 = step:<call_identity>:1
  2 = step:<call_identity>:2
  3 = step:<call_identity>:3
```

While running, it might look like:

```text
call:<call_identity>:index
  0 = call:<call_identity>:record
  1 = committed:<call_identity>:1
  2 = task:<task_identity>
  3 = step:<call_identity>:3
```

When complete:

```text
call:<call_identity>:index
  0 = call:<call_identity>:record
  1 = committed:<call_identity>:1
  2 = committed:<call_identity>:2
  3 = committed:<call_identity>:3
```

If failed:

```text
call:<call_identity>:index
  0 = call:<call_identity>:record
  1 = committed:<call_identity>:1
  2 = failure:<call_identity>:2
  3 = step:<call_identity>:3
```

The guiding rule:

```text
The process state must be readable from one index.
```

## Slot lifecycle

A step slot is not complete when the worker produces a result. It is complete only when scrivener commits that result.

The lifecycle is:

```text
step → worker task → worker result → scrivener task → committed
```

Expanded:

```text
step:<call_identity>:N
  → task:<worker_task_identity>
  → response|transform|retrieval:<call_identity>:N
  → task:<scrivener_task_identity>
  → committed:<call_identity>:N
```

Failure may happen at either worker or scrivener stage:

```text
failure:<call_identity>:N
```

## Result classes

There are two categories of result-like keys.

Worker-produced intermediate results:

```text
response:<call_identity>:<step_no>
transform:<call_identity>:<step_no>
retrieval:<call_identity>:<step_no>
```

Terminal slot states:

```text
committed:<call_identity>:<step_no>
failure:<call_identity>:<step_no>
```

The orchestrator should treat only `committed` and `failure` as terminal slot states.

Worker results are inputs to scrivener, not final process states.

## Orchestrator loop

Pseudo-flow:

```text
1. Select oldest call index from active zset.
2. Read call:<identity>:index.
3. Find the first slot that is not committed and not failure.
4. Inspect the key kind in that slot.

If slot contains step:<call_identity>:N:
  - create worker task
  - write task:<task_identity>
  - push task key to worker queue
  - replace slot with task:<task_identity>
  - bump zset score to now

If slot contains task:<task_identity>:
  - open the task
  - if it is a worker task:
      check for response/transform/retrieval:<call_identity>:N
      check for failure:<call_identity>:N
      if worker result exists:
          create scrivener task
          push scrivener task key
          replace slot with task:<scrivener_task_identity>
      if failure exists:
          replace slot with failure key
          terminal failure
  - if it is a scrivener task:
      check for committed:<call_identity>:N
      check for failure:<call_identity>:N
      if committed exists:
          replace slot with committed key
      if failure exists:
          replace slot with failure key
          terminal failure
  - bump zset score to now

If all executable slots are committed:
  - remove call from active zset or score it into terminal pasture.
```

## Deterministic keys

The design reintroduces semantic Redis keys, but only for deterministic process position.

This is acceptable because these keys do not replace model content. They encode where a result belongs in the process chain.

Good semantic keys:

```text
response:<call_identity>:<step_no>
transform:<call_identity>:<step_no>
retrieval:<call_identity>:<step_no>
committed:<call_identity>:<step_no>
failure:<call_identity>:<step_no>
```

These are better than juggling hash values because the expected key is directly derivable from call identity and step number.

## Task records

Tasks may still carry explicit expected keys for debugging and clarity.

Worker task example:

```json
{
  "identity": "01KW...",
  "call_identity": "01KV...",
  "step_no": 1,
  "package": "worker",
  "action": "execute_step",
  "step_key": "step:01KV...:1",
  "success_kinds": ["response", "transform", "retrieval"],
  "failure_key": "failure:01KV...:1"
}
```

Scrivener task example:

```json
{
  "identity": "01KW...",
  "call_identity": "01KV...",
  "step_no": 1,
  "package": "scrivener",
  "action": "commit_step",
  "input_key": "response:01KV...:1",
  "success_key": "committed:01KV...:1",
  "failure_key": "failure:01KV...:1"
}
```

The orchestrator can derive expected keys, but explicit fields make inspection easier.

## Worker and scrivener behavior

Workers and scrivener become dumb producers.

Worker:

```text
consume task
read task and step
produce deterministic response/transform/retrieval or failure key
exit
```

Scrivener:

```text
consume task
read input result
write durable ledger/sqlite/export row
produce committed or failure key
exit
```

Neither needs to post back to the orchestrator for normal continuation.

The orchestrator discovers progress by inspecting keys.

## Human-debuggable inspection

A future command should make the state obvious:

```bash
asc calls inspect <call-id>
```

Example output:

```text
call:01KW...:index

0  call       call:01KW...:record       ready
1  committed  committed:01KW...:1       done
2  task       task:01KX...              waiting for response:01KW...:2
3  step       step:01KW...:3            not dispatched
```

This command should answer the operator’s real question:

```text
What is the next unfinished slot, and what key is expected next?
```

## Final invariant

```text
The call index is the workflow state machine.
The zset is the scheduler.
Workers and scrivener are dumb executors.
A step slot is not done until it is committed or failed.
```
