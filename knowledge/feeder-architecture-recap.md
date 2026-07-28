# AutoScribe Feeder Architecture Recap

**Date:** 12 July 2026  
**Status:** Agreed direction for the Python `obs` feeder package

## Purpose

The new `obs` package will replace the current Node.js CLI functions that connect an Obsidian vault to the AutoScribe pipeline.

The repository layout should mirror the existing pipeline package:

```text
~/AutoScribe/
  pipeline/
    src/asc/
  feeder/
    src/obs/
```

The name **feeder** is complementary to **pipeline**:

- `obs` / feeder owns vault-facing selection, scanning, upload preparation, enqueue requests, exports, and writeback.
- `asc` / pipeline owns execution, queues, workers, orchestration, results, and the execution ledger.

## Main architectural decision

Do not make Obsidian interact directly with SQLite.

Obsidian should write small, timestamped JSON request files to a single transient directory. Python will consume those requests, scan the indicated vault, perform the required operation, and write durable state to SQLite.

This avoids:

- native SQLite modules inside Obsidian/Electron;
- Electron ABI and packaging problems;
- mutable JSON manifests spread across vault-specific directories;
- vault-name and path-resolution conventions;
- duplicate state in both JSON and SQLite;
- complicated synchronization between JavaScript and Python.

## Storage split

### Transient request transport

Use a per-user temporary directory:

```text
/tmp/autoscribe-$UID/
  inbox/
  processing/
  failed/
```

An alternative is:

```text
/run/user/$UID/autoscribe/
```

`/tmp/autoscribe-$UID` is simpler and is the initial recommendation.

The request files are commands, not durable records. Successful requests can be deleted after processing. Failed requests remain available for inspection until cleaned up or the machine reboots.

### Durable state

Store durable feeder state in SQLite:

```text
~/.local/share/autoscribe/feeder.sqlite
```

SQLite becomes the authoritative record of:

- vaults;
- selections;
- upload attempts;
- uploaded instructions and plans;
- dispatched runs;
- call/result relationships needed by the feeder;
- exports;
- writeback and writenew operations;
- request processing history;
- failures and error details.

The exact schema can be designed after the request contracts are settled.

## Request envelope

Every Obsidian request should be self-contained and use one stable envelope:

```json
{
  "version": 1,
  "operation": "dispatch-run",
  "created_at": "2026-07-12T08:31:14.482913+07:00",
  "vault_root": "/home/jeremy/Studio/Articles",
  "payload": {
    "plan_slug": "plan.live-llm-smoke-test.kf2oed",
    "content_slugs": [
      "cnt.corner-office.94vji1"
    ]
  }
}
```

Required envelope fields:

```text
version
operation
created_at
vault_root
payload
```

`vault_root` removes the need for vault-name hashes, current-vault manifests, or implicit path reconstruction. Python receives the authoritative vault path with every request.

The `payload` schema varies by operation.

## Example operations

### Upload instructions

```json
{
  "version": 1,
  "operation": "upload-instructions",
  "created_at": "2026-07-12T08:40:00+07:00",
  "vault_root": "/home/jeremy/Studio/Articles",
  "payload": {
    "slugs": [
      "ins.example.abc123"
    ],
    "force": false
  }
}
```

### Upload plans

```json
{
  "version": 1,
  "operation": "upload-plans",
  "created_at": "2026-07-12T08:42:00+07:00",
  "vault_root": "/home/jeremy/Studio/Articles",
  "payload": {
    "plan_slugs": [
      "plan.live-llm-smoke-test.kf2oed"
    ]
  }
}
```

The payload should identify plans by their stable slug or carry the complete plan definition. The preferred contract should be chosen after reviewing the existing plan-selection code.

### Dispatch run

```json
{
  "version": 1,
  "operation": "dispatch-run",
  "created_at": "2026-07-12T08:45:00+07:00",
  "vault_root": "/home/jeremy/Studio/Articles",
  "payload": {
    "plan_slug": "plan.live-llm-smoke-test.kf2oed",
    "content_slugs": [
      "cnt.corner-office.94vji1"
    ]
  }
}
```

### Writeback

```json
{
  "version": 1,
  "operation": "writeback",
  "created_at": "2026-07-12T09:00:00+07:00",
  "vault_root": "/home/jeremy/Studio/Articles",
  "payload": {
    "result_identities": [
      "01KX..."
    ]
  }
}
```

### Writenew

```json
{
  "version": 1,
  "operation": "writenew",
  "created_at": "2026-07-12T09:05:00+07:00",
  "vault_root": "/home/jeremy/Studio/Articles",
  "payload": {
    "result_identities": [
      "01KX..."
    ],
    "target_dir": "Findings"
  }
}
```

## Atomic request writing

Obsidian must not expose a partially written JSON file to Python.

Write each request to a temporary filename first:

```text
/tmp/autoscribe-1000/inbox/.tmp-01KX...
```

Then rename it after the JSON has been fully written and flushed:

```text
/tmp/autoscribe-1000/inbox/20260712T083114.482913-01KX....json
```

Rename within the same filesystem is atomic.

The filename is only for ordering and collision avoidance. Python should trust the request content, not parse semantic state from the filename.

## Request processing lifecycle

Python processes each request as follows:

```text
scan inbox
→ atomically rename request into processing
→ parse JSON
→ validate envelope and operation payload
→ validate vault_root
→ scan the vault/repository as required
→ perform the SQL transaction
→ invoke asc upload/enqueue/export commands when required
→ record the outcome in SQLite
→ delete the request on success
```

On failure:

```text
processing/request.json
→ failed/request.json
```

The database should also record the failure, including:

```text
request identity or filename
operation
vault root
failure boundary
exception type
error message
created_at
failed_at
```

A bad request must fail loudly. There should be no fallback vault, fallback manifest, or inferred operation.

## Claiming and concurrency

Claim a request by atomic rename:

```text
inbox/request.json
→ processing/request.json
```

This prevents two feeder processes from handling the same request.

Initially, the feeder can process requests serially. Concurrency is unnecessary until the contracts and SQL transactions are stable.

If the process crashes after claiming a request, the request remains in `processing/`. A startup recovery rule can later move stale processing files back to `inbox/` or mark them failed.

## Package responsibilities

A likely package structure is:

```text
feeder/
  pyproject.toml
  src/
    obs/
      __init__.py
      cli.py
      config.py
      requests/
        __init__.py
        envelope.py
        paths.py
        claim.py
        process.py
      vault/
        __init__.py
        repo.py
        scan.py
        slugs.py
        frontmatter.py
      operations/
        __init__.py
        upload_instructions.py
        upload_plans.py
        dispatch_run.py
        writeback.py
        writenew.py
      storage/
        __init__.py
        database.py
        schema.py
        repositories.py
      pipeline/
        __init__.py
        asc.py
      models/
        __init__.py
        request.py
        selection.py
        operation.py
```

This is only a working layout. Avoid speculative abstractions and merge modules when a separate file adds ceremony without clarity.

### `obs.requests`

Owns:

- request-directory creation;
- atomic claim/move/delete operations;
- envelope validation;
- dispatch by `operation`;
- failure handling.

### `obs.vault`

Owns:

- validating `vault_root`;
- finding the git root when necessary;
- scanning Markdown files;
- reading frontmatter;
- building a slug index;
- checking git state;
- locating writeback targets.

### `obs.operations`

Owns the actual feeder workflows:

- instruction upload;
- plan upload;
- prompt dispatch;
- writeback;
- writenew.

Each operation should accept a validated request model and explicit dependencies. It should not search for hidden manifests.

### `obs.storage`

Owns feeder SQLite state and transactions.

No Obsidian JavaScript should query this database directly.

### `obs.pipeline`

Provides the small boundary to `asc`, probably through subprocess calls initially.

Keep this boundary explicit so a future in-process Python API can replace subprocess calls without changing operation code.

## CLI direction

The first useful CLI surface is:

```bash
obs process
obs daemon
obs status
obs retry-failed <request-file>
```

Possible meanings:

### `obs process`

Process all currently queued requests once, then exit.

Useful for:

- development;
- debugging;
- smoke tests;
- manual invocation from Obsidian.

### `obs daemon`

Continuously process requests, sleeping or blocking when the inbox is empty.

This can be added after `process` is stable.

### `obs status`

Report:

- inbox count;
- processing count;
- failed count;
- database path;
- recent failures;
- known vaults.

### `obs retry-failed`

Move a corrected or selected failed request back to the inbox.

## Existing custody rules to preserve

The Python port should retain the useful guardrails from the current CLI.

### Instruction upload

- Select only intended instruction files.
- Validate slugs.
- Refuse ambiguous duplicate slugs.
- Convert through Pandoc where required.
- Preserve the existing policy about committing instruction upload custody.
- Do not silently upload files that failed validation.

### Plan upload

- Validate the complete plan before sending it.
- Preserve 1-based step ordering and the current plan/step contract.
- Record successful upload state in SQLite rather than mutating a shared JSON manifest.

### Dispatch run

- Resolve content slugs against the explicit `vault_root`.
- Fail on missing or duplicate slugs.
- Emit valid NDJSON to the existing `asc` upload/enqueue boundary.
- Record every dispatched prompt/plan pair durably.

### Writeback

- Resolve the target by slug.
- Refuse a dirty target.
- Refuse a target that has never been committed if that remains the intended rule.
- Preserve frontmatter.
- Replace only the Markdown body.
- Set `status: ai-generated` or the current agreed metadata.
- Record export success only after the file write succeeds.

### Writenew

- Handle provisional `prv.*` results.
- Never overwrite an existing file.
- Derive a reasonable filename from result/source metadata.
- Record export success only after creation succeeds.

## What is being discarded

The next implementation should not preserve the current manifest layout merely for compatibility.

Discard or retire:

- vault-keyed manifest directories;
- basename-plus-hash vault identities for transport;
- `current-run.json` as shared mutable state;
- plan/run/writeback/writenew JSON files used as databases;
- `.autoscribe` workflow state inside the vault;
- path guessing based on `pwd` alone;
- duplicated upload/export state in JSON and SQLite.

JSON remains only as the transient request boundary between Obsidian and Python.

## Suggested implementation sequence

### Phase 1 — establish the feeder package

1. Create:

   ```text
   ~/AutoScribe/feeder/src/obs
   ```

2. Add `pyproject.toml` and an `obs` console command.
3. Implement configuration for:
   - request root;
   - SQLite path;
   - `asc` executable;
   - Pandoc executable.
4. Implement request envelope models.
5. Implement atomic inbox claiming.
6. Add `obs process` with a placeholder operation dispatcher.

### Phase 2 — SQLite foundation

1. Create the first feeder schema.
2. Add request history and failure tables.
3. Add a transaction wrapper.
4. Record every claimed request before executing it.
5. Mark requests successful or failed.

Do not design the entire future client database yet. Add only tables needed by the first ported operations.

### Phase 3 — vault scanning

1. Validate the explicit `vault_root`.
2. Scan Markdown files.
3. Parse frontmatter.
4. Build the slug index.
5. Detect duplicate slugs.
6. Add git-state checks needed for upload and writeback.

### Phase 4 — port one complete path

Port `dispatch-run` first because it exercises the central architecture:

```text
Obsidian request
→ Python request claim
→ vault scan
→ slug resolution
→ content extraction
→ NDJSON generation
→ asc enqueue
→ SQLite record
```

Once this works, the request transport and storage boundaries are proven.

### Phase 5 — uploads

Port:

1. `upload-instructions`;
2. `upload-plans`.

Keep Pandoc and `asc` subprocess calls explicit.

### Phase 6 — result handling

Port:

1. `writeback`;
2. `writenew`.

Preserve the existing git and overwrite guardrails.

### Phase 7 — Obsidian JavaScript cleanup

Replace the current operational JavaScript with small request writers.

Each Obsidian command should only:

1. collect the user's selection;
2. construct a request object;
3. write it atomically to the feeder inbox;
4. optionally invoke `obs process` or rely on `obs daemon`;
5. display a simple acknowledgement or later status view.

No upload, writeback, git, SQLite, or pipeline logic should remain in Obsidian JavaScript.

## Decisions still to make

These can be settled during implementation rather than designed in advance:

1. Whether the temporary root should be `/tmp/autoscribe-$UID` or `/run/user/$UID/autoscribe`.
2. Whether successful request metadata should remain in SQLite indefinitely or be periodically pruned.
3. How long stale files in `processing/` remain before recovery.
4. Whether plan requests carry full plan JSON or refer to a plan source file/slug.
5. Whether `obs process` invokes one request or drains the complete inbox.
6. Whether the daemon uses polling, filesystem notifications, or a simple blocking strategy.
7. Which tables belong in the feeder database versus the existing pipeline ledger.

The guiding rule is to choose the smallest contract that supports the current operation and avoid anticipating the production Electron client prematurely.

## Final architecture

```text
Obsidian
  edits Markdown
  gathers user selections
  writes timestamped JSON commands to /tmp

obs feeder
  claims and validates commands
  scans the explicit vault
  performs upload, enqueue, export, and writeback operations
  records durable feeder state in SQLite
  invokes asc through a narrow boundary

asc pipeline
  owns execution queues
  orchestrates steps
  runs workers and engines
  persists pipeline results and failures
```

The key simplification is:

> Obsidian writes commands. Python owns operations and durable state. The pipeline owns execution.

