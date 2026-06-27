Here’s the recap for tomorrow’s dev branch work.

```text id="zq40zi"
Proactive orchestrator design recap

Current plan:
- Finish and merge the current message-driven completion/export fix first.
- Start the proactive orchestrator on a fresh dev branch after master is stable.

Target runtime shape:
- 1 orchestrator
- 1 scrivener
- N workers

Rationale:
- Orchestrator is not the bottleneck; it only decides and posts tasks.
- Scrivener should remain single-instance because SQLite has one writer.
- Workers are the only fan-out target because they wait on LLM/script/RAG work.

Retire cursor:
- Cursor can go away.
- Its jobs are replaced by:
  - orchestrator call zset for scheduling/liveness
  - call index for durable call progress
  - pending markers for duplicate suppression
  - result keys plus ledger/export rows for durable facts

New scheduler:
- Add a Redis sorted set:

    control:orchestrator:calls

- Member:

    <call_identity>

- Scores:

    NEW_SCORE  = far past, probably 0
    now_ns()   = active/recently touched
    DONE_SCORE = far future

Enqueuer:
- Save call:<identity>:record.
- Add <identity> to control:orchestrator:calls with NEW_SCORE.
- Do not create cursor.

Orchestrator loop:
- Select oldest call with score below DONE_SCORE.
- Touch it by setting score to now_ns().
- Reconcile durable state.
- Post at most one next task.
- On completed or terminal-failed export, set score to DONE_SCORE.

Core rule:
- The orchestrator should be a reconciler, not a message handler.
- It should ask:

    What durable facts already exist?
    What durable fact is missing next?
    What task should create that missing fact?

Durable facts:
- call:<identity>:record
- call:<identity>:index
- step:<plan_identity>:<n>
- response:<identity>:<n>
- transform:<identity>:<n>
- retrieval:<identity>:<n>
- failure:<identity>:<n>
- committed:<task_identity>
- exports table row for final result identity

Pending markers:
- Needed even with one orchestrator, because workers may be waiting on LLM calls.
- Pending suppresses duplicate task posting while external work is in flight.
- Pending is not progress and should never be treated as truth.

Possible pending keys:
- pending:<call_identity>:write_call
- pending:<call_identity>:worker:<step_number>
- pending:<call_identity>:write_step:<step_number>
- pending:<call_identity>:write_export

Reconciler checklist:

1. New call
   - If call index does not exist:
     - materialize plan
     - create call:<identity>:index
     - slot 0 = call:<identity>:record
     - slots 1..N = step:<plan_identity>:n
     - post scrivener write_call
     - set pending write_call
     - touch call

2. Call row write
   - If call index exists but call ledger row is not written:
     - if no pending write_call, post scrivener write_call
     - otherwise wait/touch

3. Worker step
   - If first unresolved slot contains step:<plan_identity>:n:
     - if no pending worker:n, post worker task
     - set pending worker:n
     - touch call

4. Worker result
   - If worker result exists for call identity + step number:
     - validate outcome.status against result key kind
       - SUCCESS -> response|transform|retrieval
       - FAILURE -> failure
     - replace call index slot n with result key
     - clear pending worker:n
     - post scrivener write_step
     - set pending write_step:n
     - touch call

5. Step ledger write
   - If slot n contains result key but step ledger row is missing:
     - if no pending write_step:n, post scrivener write_step
     - otherwise wait/touch

6. Advance after step ledger write
   - If slot n contains failure key and step row is written:
     - post write_export using failure key
     - set pending write_export
     - touch call

   - If slot n contains success result key and more steps remain:
     - post next worker task
     - set pending worker:n+1
     - touch call

   - If slot n contains success result key and no more steps remain:
     - final_key = latest result key
     - post write_export using final_key
     - set pending write_export
     - touch call

7. Export row
   - If exports table has row for final result identity:
     - clear pending write_export
     - set call score to DONE_SCORE

Critical invariant:
- A call is not done until the export row exists.
- The final export write uses the final result key, not the call record key.
- The final result row contains the cell row identity, so the table chain can be queried from either end.

Naming cleanup:
- Stop using call_completed to mean export write.
- Prefer:

    SCRIVENER_WRITE_EXPORT = "write_export"

- Keep meanings separate:

    write_call      -> calls table
    write_step      -> steps table
    write_export    -> exports table
    mark_completed  -> optional future calls-table status update

Message role:
- Messages can remain temporarily as wake-up signals.
- Long-term, the orchestrator should not depend on message contents for correctness.
- It should reconcile the oldest active call from the zset and durable state.

Suggested module shape:

asc/orchestrator/
  daemon.py
  schedule.py       # call zset: add, next, touch, finish
  reconcile.py      # central state machine
  state.py          # observed durable facts for a call
  pending.py        # duplicate suppression
  dispatch.py       # save task + post to inbox
  call_index.py
  materialize.py
  tasks/
    worker.py
    scrivener.py
  contracts.py
  errors.py

Migration order:
1. Merge current working message-driven export fix to master.
2. Create a new dev branch for proactive orchestration.
3. Add orchestrator call zset.
4. Update enqueuer to insert new calls with NEW_SCORE.
5. Add schedule.py.
6. Add pending.py.
7. Add reconcile.py with terminal export recovery first.
8. Move next-step decisions from handlers into reconcile.py.
9. Move write-step decisions from handlers into reconcile.py.
10. Remove cursor.
11. Make messages optional wake signals only.
```

Branch name idea:

```text id="ia4m41"
dev/proactive-orchestrator
```

Commit seed for the first commit on that branch:

```text id="d9gcwg"
Introduce call scheduler for proactive orchestration
```
