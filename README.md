# AutoScribe

AutoScribe owns the on-demand lifecycle in `asc.ssh_jobs`, not a resident queue
worker. Common owns LLM providers. Control owns authored configuration.
Extensions owns registered executables and resources. SQLite records execution
claims and receipts; it never reconstructs runtime payloads.

## Canonical public model

```python
from asc.models.call import Call
call = Call.load(call_id)
original = call.source.original_text
processing = call.source.processing_text
metadata = call.source.metadata
previous = call.result(previous_position)
request = call.steps[str(previous_position)].request
final = call.final_result
```

The installed forward package is `asc`. There is no `autoscribe` package alias.
The existing `asc` command and external native input/response protocol names do
not change. `Call`, `Source`, `Plan`, `Step`, `Instruction`, `StepInput`,
`ComponentContext`, `Invocation`, `ProviderRequest`, `ProviderResponse`,
`StepResult`, `StepExecution`, `Receipt` and `ErrorInfo` are Pydantic models in
`asc.models.call`. No per-script result subclass is required.

`source.original_text` is the exact submitted UTF-8 text, including any original
frontmatter and whitespace. It is never an intermediate output or automatically
inferred passage body. `processing_text` is the independently checksummed text
selected by preprocessing, including expansion where present. Explicitly absent
source is represented by `None` only for non-executable intake failures.

`plan` is a typed accepted snapshot with Control revision, step identities,
instruction bodies and source commit/checksum provenance. Runtime requests and
results are distinct objects under `steps`, indexed by string step position.
Step positions need not be contiguous. `final_position` selects a result; it
never replaces the original source. `requested_plan_id` survives failed Control
resolution. `baggage` retains opaque authenticated transport coordination.

The provider request is the complete assembled Responses API kwargs (resolved
model, input/messages, instructions and parameters), captured through Common's
request observer before any provider request. It contains no credentials.
Recording a request does not claim the provider accepted or completed it.
Provider result metadata separately retains actual model, completion status,
response/request IDs and usage. Unknown outcomes remain explicit typed errors.

## Executable component protocol v1

An executable receives exactly one JSON object on stdin:

```text
Invocation {
  protocol: "asc.component.v1",
  context: {
    call_id, plan_id, plan_revision, plan_snapshot_sha256,
    step_id, position, engine_kind, engine, component,
    configuration, input_position, release_id
  },
  input: { text, data, assets }
}
```

`input_position` is null for source input and otherwise references the preceding
result selected by the accepted plan. The context identifies the call without
copying it. Every component kind receives this same context and typed input.
RAG remains explicitly unimplemented.

Stdout must be exactly one serialized `StepResult` with protocol
`asc.step-result.v1`. It identifies call/step/position/component/release and
carries status, optional text, JSON data, asset references, provider metadata and
error information. Diagnostics go to stderr. Plain text, malformed JSON,
unknown fields and foreign result ownership fail; there is no old text adapter.

```python
#!/usr/bin/env python3
import sys
from asc.models.call import Invocation

invocation = Invocation.model_validate_json(sys.stdin.read())
call = invocation.context.load_call()
result = invocation.result(data={
    "original": call.source.original_text,
    "generated": invocation.input.text,
    "source_identity": call.source.identity,
    "tone": call.source.metadata.get("tone"),
})
print(result.model_dump_json())
```

Register the executable using the existing Extensions `registry.json`, then
reference its name from a Control script step. No worker, Redis or result-handler
change is required. Python scripts receive the selected interpreter directory
on PATH and the already-selected application/Common module roots on PYTHONPATH.
Installed releases use their own bundled modules, not a development checkout.
Non-Python executables can implement the same JSON protocol; its JSON schemas
are available from `Invocation.model_json_schema()` and
`StepResult.model_json_schema()`.

The demonstration under `app/tests/pair_fixture.py` is test-only, not a
production training-pair generator. The following executable consumes its typed
structured output without knowing which component produced it.

## Redis ownership and retention

`RuntimeStore` is the only key/serialization/hydration owner. One string value at
`asc:call:<call identity>` contains the `asc.call.v1` aggregate, including source,
plan, invocation records, requests, results, final reference, errors and receipt.
No scan is required to discover a known call's data. Scripts use `Call.load` or
`context.load_call`, never storage key strings or SQLite.

Model boundaries validate both reads and writes. Missing/expired, malformed,
unavailable and concurrent updates raise `MissingRecord`, `InvalidRecord`,
`StorageUnavailable` and `ConcurrentUpdate`. Compare-and-set writes prevent stale
updates. Accepted source/configuration and recorded step inputs/requests/results
are immutable. No historical hash/schema reader or ledger recovery exists.

`AUTOSCRIBE_RUNTIME_RETENTION_SECONDS` is the single configurable policy setting.
Its authoritative default is 72 hours in `asc.settings`. Each accepted call pins
its selected value. Accepted, executing, uncertain and delivery-pending data has
no TTL. Completion alone does not permit expiry. After checksum-authorized
cleanup commits its durable acknowledgement, the model atomically applies one
fixed deadline to the whole record. Cleanup retries do not extend that deadline.
A Redis failure after the ledger acknowledgement is retried by idempotent
cleanup; data stays persistent until that operation succeeds. Expiry never
causes provider replay or implies delivery acknowledgement.

SQLite schema remains the execution ledger. New `call_keys` facts contain one
`runtime` reference, not content/baggage payloads. Historical facts are not
migrated. Vault/Git permanent source/output storage is unchanged.

## Releases

Use the existing `release.py` and `install-release.py`. Exact committed source
exports, package/resource hashes, full component revisions and client protocols
are recorded in the immutable release manifest. Activation refuses non-cleaned,
pending or unowned work. Historical releases remain explicit rollback material,
never automatic fallback implementations. Scripts and accepted jobs remain bound
to the accepting immutable release. Unknown provider outcomes require explicit
reconciliation and are never automatically retried.
