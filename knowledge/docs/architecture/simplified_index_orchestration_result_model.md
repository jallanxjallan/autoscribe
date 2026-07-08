# Simplified Index-Driven Orchestration with One Result Model

## Purpose

This note merges the proactive orchestrator recap and the index-driven process-chain recap into one simpler target design.

The core simplification is that the orchestrator no longer has to reason about separate worker output models such as `Response`, `Transform`, `Retrieval`, and `Failure` as Redis key kinds.

There is one universal result envelope:

```text
result:<identity>[:suffix]
```

The serialized payload inside that result can still represent an LLM response, a script transformation, a RAG retrieval, or a failure. But those are result attributes, not top-level Redis key kinds.

The orchestrator only deals with five runtime key kinds:

```text
call
step
task
result
commit
```

## Final invariant

```text
The call index is the workflow state machine.
The zset is the scheduler.
Tasks record work in flight.
Results record what a task produced.
Commits record that scrivener made a durable write.
Workers and scrivener remain dumb executors.
```

## Runtime shape

```text
1 orchestrator
1 scrivener
N workers
```

The orchestrator is not the bottleneck. It only inspects durable state, decides the next obvious move, writes a task, and rotates to the next call.

Scrivener remains single-instance because SQLite has one writer.

Workers are the fan-out target because they spend time waiting on LLM, script, or RAG work.

## Retire cursor

Cursor goes away.

Its jobs are replaced by:

```text
call zset       scheduling and liveness
call index      durable readable process state
task records    work currently in flight
result records  outputs from completed tasks
commit records  confirmation of durable scrivener writes
ledger/export   durable application facts
```

Messages may remain as wake-up hints during migration, but they must not be required for correctness.

## Active call zset

Use one sorted set:

```text
control:orchestrator:calls
```

Members can be either the call identity or the call index key. Prefer the call identity if the key can be derived consistently:

```text
<call_identity>  score=<last_touched_at>
```

Scores:

```text
NEW_SCORE   = far past, probably 0
now_ns()    = active / recently touched
DONE_SCORE  = far future
```

The orchestrator selects the oldest score below `DONE_SCORE`, reconciles one move, then bumps the score to `now_ns()` unless the call is terminal.

This prevents the orchestrator from hammering a blocked call and naturally rotates through active calls.

## Call index as process state

The call index is the readable state machine:

```text
call:<call_identity>:index
  0 = call:<call_identity>:record
  1 = step:<plan_identity>:1
  2 = step:<plan_identity>:2
  3 = step:<plan_identity>:3
```

A running call might look like:

```text
call:<call_identity>:index
  0 = call:<call_identity>:record
  1 = commit:<commit_identity>
  2 = task:<task_identity>
  3 = step:<plan_identity>:3
```

A completed call might look like:

```text
call:<call_identity>:index
  0 = call:<call_identity>:record
  1 = commit:<commit_identity>
  2 = commit:<commit_identity>
  3 = commit:<commit_identity>
```

A failed call might look like:

```text
call:<call_identity>:index
  0 = call:<call_identity>:record
  1 = commit:<commit_identity>
  2 = result:<result_identity>
  3 = step:<plan_identity>:3
```

The failed slot is a `result` key whose mandatory fields say `status="failure"`.

## Slot lifecycle

A step slot is not done when the worker produces a result. It is done only when scrivener commits that result, or when a result records a terminal failure.

Normal successful lifecycle:

```text
step -> worker task -> worker result -> scrivener task -> commit
```

Expanded:

```text
step:<plan_identity>:N
  -> task:<worker_task_identity>
  -> result:<worker_result_identity>
  -> task:<scrivener_task_identity>
  -> commit:<commit_identity>
```

Failure lifecycle:

```text
step:<plan_identity>:N
  -> task:<task_identity>
  -> result:<result_identity status="failure">
```

A worker failure produces a `result` with `status="failure"`.

A scrivener failure can also produce a `result` with `status="failure"`, tied to the scrivener task that failed.

## Five key kinds

The orchestrator should switch only on key kind:

```text
call     original call record and call index
step     materialized plan step waiting to be dispatched
task     worker or scrivener work in flight
result   universal task output envelope
commit   scrivener success marker after durable write
```

It should not switch on these as Redis key kinds anymore:

```text
response
transform
retrieval
failure
committed
```

Those meanings move into model fields.

## Universal Result model

There should be one result model for all worker outputs and task failures.

Conceptual shape:

```python
class Result(RedisModel):
    kind: ClassVar[str] = "result"

    identity: str
    task_key: str
    call_identity: str
    step_no: int
    status: Literal["success", "failure"]
    product: Literal["response", "transform", "retrieval", "failure"]
    payload_json: str
```

### Mandatory fields

The fields the orchestrator needs for decisions are:

```text
task_key       which task produced this result
call_identity  which call this result belongs to
step_no        which call-index slot this result belongs to
status         success or failure
product        response, transform, retrieval, or failure
payload_json   JSON serialization of the actual output object
```

`payload_json` is deliberately opaque to the orchestrator except when a later step needs the content. The result envelope gives the orchestrator enough information to decide whether to advance, commit, export, or stop.

The important point is that `response`, `transform`, `retrieval`, and `failure` are no longer model classes the orchestrator has to route by. They are serialized payload types inside one `Result` record.

## Result payload examples

LLM response result:

```json
{
  "identity": "01RY...",
  "task_key": "task:01TW...",
  "call_identity": "01CA...",
  "step_no": 1,
  "status": "success",
  "product": "response",
  "payload_json": "{\"content\":\"...\",\"model\":\"...\"}"
}
```

Script transform result:

```json
{
  "identity": "01RY...",
  "task_key": "task:01TW...",
  "call_identity": "01CA...",
  "step_no": 2,
  "status": "success",
  "product": "transform",
  "payload_json": "{\"content\":\"...\",\"script\":\"scripts.insert_footer\"}"
}
```

RAG retrieval result:

```json
{
  "identity": "01RY...",
  "task_key": "task:01TW...",
  "call_identity": "01CA...",
  "step_no": 3,
  "status": "success",
  "product": "retrieval",
  "payload_json": "{\"content\":\"...\",\"sources\":[...] }"
}
```

Failure result:

```json
{
  "identity": "01RY...",
  "task_key": "task:01TW...",
  "call_identity": "01CA...",
  "step_no": 2,
  "status": "failure",
  "product": "failure",
  "payload_json": "{\"content\":\"script failed: ...\",\"error_type\":\"RuntimeError\"}"
}
```

## Task records

The call index must record the task while work is in flight.

A task should carry enough expected-output information to make inspection and reconciliation obvious.

Worker task:

```json
{
  "identity": "01TW...",
  "package": "worker",
  "action": "execute_step",
  "call_identity": "01CA...",
  "step_no": 1,
  "step_key": "step:01PL...:1",
  "result_key": "result:01RY..."
}
```

Scrivener task:

```json
{
  "identity": "01TS...",
  "package": "scrivener",
  "action": "commit_step",
  "call_identity": "01CA...",
  "step_no": 1,
  "input_key": "result:01RY...",
  "commit_key": "commit:01CM...",
  "result_key": "result:01RF..."
}
```

For scrivener:

```text
commit_key  expected on success
result_key  expected on failure
```

This keeps the orchestrator simple:

```text
slot contains task -> open task -> check task.commit_key or task.result_key
```

The expected keys can be deterministic or generated. The task records the truth either way.

## Commit model

A commit means scrivener successfully wrote a durable fact.

Conceptual shape:

```python
class Commit(RedisModel):
    kind: ClassVar[str] = "commit"

    identity: str
    task_key: str
    call_identity: str
    step_no: int | None
    table_name: str
    input_key: str
```

Commit replaces the old `committed` kind.

Use `commit`, not `committed`, because it is a noun-like runtime fact and keeps the key kind short.

## Reconciler loop

The orchestrator is a reconciler, not a callback handler.

It asks:

```text
What durable facts already exist?
What durable fact is missing next?
What task should create that missing fact?
```

Pseudo-flow:

```text
1. Select oldest active call from control:orchestrator:calls.
2. Read call:<identity>:index.
3. Find the first unfinished slot.
4. Inspect only the key kind in that slot.
```

### If the slot contains `step`

```text
- create worker task
- save task:<task_identity>
- push task key to worker queue
- replace slot with task:<task_identity>
- bump zset score to now
```

### If the slot contains `task`

Open the task.

If it is a worker task:

```text
- check task.result_key
- if missing, wait and bump zset score
- if present, open result
- if result.status == "failure":
    - replace slot with result key
    - write/export failure as terminal result
- if result.status == "success":
    - create scrivener commit_step task
    - save task:<scrivener_task_identity>
    - push task key to scrivener queue
    - replace slot with task:<scrivener_task_identity>
```

If it is a scrivener task:

```text
- check task.commit_key
- check task.result_key
- if neither exists, wait and bump zset score
- if result exists and result.status == "failure":
    - replace slot with result key
    - write/export failure as terminal result
- if commit exists:
    - replace slot with commit key
    - advance to next slot or export final result
```

### If the slot contains `result`

Open the result.

```text
- if result.status == "failure":
    - treat as terminal failure for this call
    - ensure export row exists for this result
    - when export exists, set call score to DONE_SCORE
- if result.status == "success":
    - this is an intermediate worker result that still needs scrivener
    - create scrivener task if none exists
```

In the clean path, a successful worker result should normally be replaced quickly by a scrivener task. A success result sitting in the index is therefore recoverable state, not the preferred steady state.

### If the slot contains `commit`

Open the commit if needed.

```text
- if more steps remain:
    - advance to next step slot
- if this is the final step:
    - ensure export row exists for the final committed input/result
    - when export exists, set call score to DONE_SCORE
```

## Export rule

A call is not done until the export row exists.

The export row should point back to the final result or final commit chain, not merely to the call record.

Recommended export source:

```text
final worker result key for the last successful committed step
or
failure result key for a terminal failure
```

For a final successful commit, the commit record should include `input_key`, so the exporter can find the final result payload without guessing.

## Human-debuggable inspection

Future command:

```bash
asc calls inspect <call-id>
```

Example output:

```text
call:01CA...:index

0  call    call:01CA...:record      ready
1  commit  commit:01CM...           done, wrote result:01RY...
2  task    task:01TW...             waiting for result:01RZ...
3  step    step:01PL...:3           not dispatched
```

The command should answer:

```text
What is the first unfinished slot?
What task is in flight?
What key is expected next?
What status/product did the result report?
```

## Suggested module shape

```text
asc/orchestrator/
  daemon.py
  schedule.py       # call zset: add, next, touch, finish
  reconcile.py      # central state machine
  state.py          # observed durable facts for a call
  dispatch.py       # save task + post to inbox
  call_index.py
  materialize.py
  tasks/
    worker.py
    scrivener.py
  contracts.py
  errors.py
```

`pending.py` may no longer be necessary if the call index records the task while work is in flight. A pending marker is only needed for work that cannot be represented as a task in the slot.

## Migration order

1. Merge current working message-driven export fix to master.
2. Create a new branch:

```text
dev/proactive-orchestrator
```

3. Add the call scheduler zset.
4. Update enqueuer to create the call index and insert the call into the zset.
5. Introduce the universal `Result` model.
6. Replace `Response`, `Transform`, `Retrieval`, and `Failure` routing with `Result.status` and `Result.product`.
7. Rename `committed` to `commit`.
8. Make task records carry expected `result_key` and/or `commit_key`.
9. Move next-step decisions into `reconcile.py`.
10. Remove cursor.
11. Make messages optional wake-up hints only.

## First commit seed

```text
Introduce proactive call scheduler

Add the active call zset used by the orchestrator to select the oldest
unfinished call, touch active calls after each reconciliation pass, and move
terminal calls to a far-future done score. This begins the transition away
from cursor-driven continuation toward index-driven reconciliation.
```
