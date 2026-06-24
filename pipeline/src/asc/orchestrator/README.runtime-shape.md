# Orchestrator runtime shape draft

The orchestrator owns only its queue.  It receives Redis keys through
`inbox.post(key)`, claims them from the orchestrator queue, and dispatches by
`key.kind`.

Canonical runtime facts are written elsewhere:

- enqueuer creates the cursor/results index and writes the initial call/prompt
- worker writes response or failure keys into assigned results-index slots
- scrivener writes the ledger and posts committed keys
- orchestrator verifies posted keys against canonical state, then routes

Failures remain in the results index.  The failure handler verifies that the
posted failure key is the canonical result for the step, then delegates policy.
This draft defaults to terminal failure by tasking scrivener to record the
stopped call; retry policy can replace that later.
