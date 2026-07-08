# Orchestrator runtime shape

The orchestrator owns only its queue. It accepts exactly two posted key kinds:

- `call:<identity>[:record]`
- `outcome:<task_identity>`

Daemon completion is never routed by concrete artifact kind. Workers and
scriveners write concrete artifacts, then post an `Outcome`.

Concrete artifacts remain payload state:

- worker success: `response|transform|retrieval:<call_identity>:<step_no>`
- worker failure: `failure:<call_identity>:<step_no>`
- scrivener success: no artifact required; the ledger write is the useful side effect
- scrivener failure: `failure:<task_identity>` or equivalent daemon-boundary record

The orchestrator loads `Outcome`, branches by `package`, `action`, and `status`,
and writes worker `result_key`/`failure_key` into the call index.
