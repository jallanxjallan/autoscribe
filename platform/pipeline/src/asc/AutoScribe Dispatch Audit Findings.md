# AutoScribe dispatch audit — publication repaired and runtime boundary verified

Audit date: 2026-09-06. Completed: stale operational Control was republished and one fresh dispatch reached runtime materialization and active-job registration. No pipeline compatibility patch was required. The first verification attempt hit an instrumentation error; the same fresh commit was retried after correcting the logger, as detailed below.

## Identity and initial state

- HHP repository: `/home/jeremy/Work/Studio/HHPLawFirm`; branch `master`.
- Dispatch: `77ec2823ce6aeaa7ec06b7acb4d72c774328a3e5`, committed 2026-09-06 20:00:30 +07:00.
- Client identity: `git-77ec2823ce6aeaa7-plan-hhp-pro-bono-position-paper-boxout-4h8n3d`.
- Source: `Content/ADB Water Controversy.md`; slug `psg.adb-water-controversy.joxea0`.
- Source blob: `6ec987c59329b2903483feb0283b8956612a6ff5`.
- Source disk and commit SHA-256: `49b329fc292f9bd2d0228703182983924908fca21f2b760498b7fd1ab192f85d`; bytes equal.
- Plan: `plan.hhp-pro-bono-position-paper-boxout.4h8n3d`.
- Inflight commit created: `ab45cd6cf631b2352b677a8cce7ab9788a04ee44`.
- Server call/process identity: `01M1VD8ZXBP9TH3KPGJ368W143`.
- Both client systemd daemons were inactive. Host Redis ran `/usr/bin/redis-server 127.0.0.1:6379`, PID 834. Redis contained zero keys immediately before the dispatch.
- HHP had unrelated dirty files; none were staged or repaired. SQLite had nine older dispatch commits without submission markers. User approved restricting selection to this audit commit.
- The audit executed `/tmp/asc-dispatch-audit/target/debug/svc dispatch-once /home/jeremy/Work/Studio/HHPLawFirm`, compiled from inspected service source, with temporary commit filtering, payload/defaults logging, and Git routing through `git.py`. It did not execute the installed daemon binary. Both edited Rust files were restored byte-for-byte afterwards.
- Receiver executable: `/home/jeremy/Python3.13Env/bin/asc`; Python imported the workspace `asc` modules. Actual exec calls are captured in the execution log.

## Observed boundaries

| Boundary | Observed input | Transformation | Observed output |
|---|---|---|---|
| Client discovery | HHP master history | Authorized exact-commit selection | Selected commit above; SQLite event 301, observed |
| Source snapshot | Source blob above | Inflight snapshot | Inflight commit above; SQLite source row 290 |
| Pandoc | Detached dispatch worktree source, dispatch defaults, ephemeral source/plan defaults | Installed `emit/dispatch_calls.lua` | One call object; exact payload linked below |
| Client send → asc receipt | JSON call keys `content`, `extra`, `identity`, `plan`, `type` | NDJSON stdin and parsing | Decoded received object equals client object field-for-field |
| Call storage | Source slug, content, metadata | Generated process identity; stored call and slugmap | Call key below |
| Control selection | Operational `/home/jeremy/.local/share/autoscribe/control.git`, `master` | `control_revision()` | `8bcfc79a0e90adab4043159d6d52b745a06d0f5d` |
| Git plan read | `plans/plan.hhp-pro-bono-position-paper-boxout.4h8n3d.json` at that commit | `_blob()` via Git objects | Wrapped JSON with `record_type`, `record_identity`, `record_content` |
| JSON decoding | Raw wrapped JSON | `control/repository.py:_plan`, `json.loads(text, parse_constant=_invalid_constant)` | Same three keys and values |
| Plan factory | Decoded dictionary | `_plan`: `Plan.from_record(record)` | Identical dictionary at factory entry |
| Constructor call | Identical dictionary | `models/control/plan.py:36`, `return cls(**record)` | TypeError during argument binding; constructor body never entered |
| Failure persistence | TypeError and process/source context | `record_failure` at record and stream boundaries | Two failure hashes; client SQLite event 302, submit_failed |

## Exact plan object

The raw Git JSON, decoded dictionary, `Plan.from_record` argument and constructor keyword mapping all have the following content (formatting below is presentation only):

```json
{
  "record_type": "plan",
  "record_identity": "plan.hhp-pro-bono-position-paper-boxout.4h8n3d",
  "record_content": {
    "label": "HHP Pro Bono Position Paper Boxout",
    "description": "Prepare a standalone client-review boxout about an HHP pro bono position paper or comparable public-interest legal intervention without implying representation of a party.",
    "steps": {
      "1": {
        "index": 1,
        "kind": "llm",
        "label": "Prepare pro bono position paper boxout",
        "engine": "chatgpt",
        "model": "sol",
        "instruction_slugs": {
          "role": "rol.redrafting-editor-role.5fpy6y",
          "context": "ctx.hhp-client-case-review.8r2m6q",
          "instructions": "tsk.prepare-pro-bono-position-paper-boxout.4h8n3d"
        }
      }
    }
  }
}
```

No intermediate helper adds `record_type`. It already exists in the immutable Git blob. The first observed Python dictionary containing it is the result of `json.loads()` in `control/repository.py:_plan` (line 166); that statement decodes the stored key rather than inventing one. Historical authoring of the blob was not observed during this dispatch, so no claim is made about the historical producer statement or its intent.

The executing Plan model accepts `identity`, `title`, `description`, `steps`, `capabilities`, and optional `scope`. This run has no successful consumer requiring the envelope discriminator. It is not part of the current canonical authoring contract.

## Instruction existence

The historical plan names these three instructions. Git inspection confirmed their declarations at the same failing Control revision:

| Identity | Git path |
|---|---|
| `rol.redrafting-editor-role.5fpy6y` | `instructions/Redrafting Editor Role.md` |
| `ctx.hhp-client-case-review.8r2m6q` | `context/HHP Client Case Review.md` |
| `tsk.prepare-pro-bono-position-paper-boxout.4h8n3d` | `instructions/Prepare Pro Bono Position Paper Boxout for Client Review.md` |

Enqueue did not reach instruction reading/materialization, because Plan construction failed first. No instruction content was normalized or converted.

## Redis evidence

The final captured snapshot contains exactly four keys:

| Key | Actual content | TTL observed immediately after creation |
|---|---|---|
| `call:01M1VD8ZXBP9TH3KPGJ368W143:record` | Hash: `content`, `created_at`, `source_identity`, `identity`, `extra_json`; exact fields linked below | 2,591,999,998 ms |
| `state:slugmap:index` | Hash maps `psg.adb-water-controversy.joxea0` to that call key | No expiry (-1) |
| `failure:01M1VD905WMKD16RZE4EWGJQHW:record` | `enqueue.record`, TypeError, process `01M1VD8ZXBP9TH3KPGJ368W143`, source/call/plan context | 604,799,998 ms |
| `failure:01M1VD9064XEHJ8XET3W7V05P4:record` | `enqueue.stream`, same TypeError; process field empty | 604,799,997 ms |

`enqueue.call.store_call` created the call and slugmap through model save and SlugMap.set. `models.process.result.record_failure` created each failure via ProcessFailure.save. The stream failure is linked by the same traced exception and subprocess, not by recency. Snapshots before and after each reached significant boundary are in the trace. No runtime, job, active index, instruction, or response keys existed at termination.

## First terminal failure and cause

`TypeError: Plan.__init__() got an unexpected keyword argument 'record_type'`, at `asc.models.control.plan.from_record`, `/home/jeremy/Work/Loom/platform/pipeline/src/asc/models/control/plan.py:36`.

The source value was a wrapped plan with `record_type: "plan"` at the immutable Git boundary. Statement `record = json.loads(text, parse_constant=_invalid_constant)` in `control/repository.py:_plan` decoded it into the same wrapped dictionary. That dictionary reached `models/control/plan.py:from_record` unchanged; `return cls(**record)` caused the TypeError above. There was no in-memory enrichment to blame.

The deployment boundary owns this mismatch. Authoring commit `5934d38b2901f445768ffa7c256a9ec85ecac3b1` already contains the flat plan and current opaque instruction identities. Operational master remained at the initial historical publication. Adding parser compatibility would conceal the stale publication rather than repair it.

## Repair

The source value was the historical wrapped JSON at operational Control master `8bcfc79a0e90adab4043159d6d52b745a06d0f5d`. The publication script's `git push "$CONTROL_PUBLISH_REMOTE" "$CONTROL_PUBLISH_BRANCH:master"` in `commit-controls.zsh` updated master to `c2f0ce9101ce54d8e530e883b5fbd5af652a1d9a`. Its selected plan now supplies the flat dictionary to `Plan.from_record()`, and construction succeeds.

The user approved publication of the existing authored migration and subsequently authorized omitting the inaccessible backup push. `commit-code.zsh` found no code changes. A temporary copy of `commit-controls.zsh`, with its root fixed to the original Control directory and its backup push omitted, published the operational paths through `git.py`. The persistent scripts, pipeline code, Plan parser, authored plans and instruction bodies were not edited by this audit.

The operational tree was verified to equal committed authoring revision `5934d38b2901f445768ffa7c256a9ec85ecac3b1` under `instructions`, `plans`, `context`, and `gates`, including identical blob IDs. Authoring and publication worktrees are clean. The actual old-to-new operational diff is **34 files, 146 insertions, 834 deletions**. The earlier 33-file summary omitted the deleted gates recap; the full review diff included it. These are previously authored migration changes, not a new runtime accommodation.

For the selected plan, publication replaces the historical envelope starting at JSON line 2 with `identity`, `title`, `description`, `steps`, and `capabilities`. Its three existing authored instructions now carry their committed opaque identities. No source-code lines required a permanent patch. The producer/publication boundary owns the repair; `Plan.from_record()` remains the direct current-format constructor.

## Fresh dispatch verification

- Fresh HHP commit: `021d59551bd1078ddb8a38260f232d9a7477ccfb` on `master`.
- Client identity: `git-021d59551bd1078d-plan-hhp-pro-bono-position-paper-boxout-4h8n3d`.
- Same source slug, path and blob `6ec987c59329b2903483feb0283b8956612a6ff5`; empty dispatch commit includes no unrelated user edits.
- Inflight source snapshot: `8f235ecfecfb21331ecd7e018b15ad9f56185d6b`.
- Submitted event commit: `cd57eca9d2c3dcf36979322e96e595df7f202eb3`.
- Successful process identity: `01M1VDTTGG4BPKVXKDJ8VESXNK`.
- Exact selected Control commit: `c2f0ce9101ce54d8e530e883b5fbd5af652a1d9a`.
- Service exit status: 0. SQLite event 305: `submitted`, 2026-09-06 13:16:58 UTC.

| Boundary | Observed input | Transformation | Observed output |
|---|---|---|---|
| Client → receiver | Same source and plan as the failing dispatch | Pandoc, NDJSON and JSON parsing | Client and receiver objects equal; both also equal the original failing run's payload |
| Control selection | Operational master | `control_revision()` | New immutable revision above |
| Git → decoded plan | Selected plan's flat JSON | `_blob()` and `json.loads()` | Exactly `identity`, `title`, `description`, `steps`, `capabilities` |
| Factory → constructor | Same five-key dictionary | `return cls(**record)` | Successful Plan; bound constructor fields are those five plus default `scope=None`; no `record_type` |
| Instruction resolution | Three opaque identities below | Git reads at the selected revision, then materialization | Three instruction hashes and lookup mappings |
| Runtime | Plan step, process identity and resolved instruction keys | `materialize_runtimes` | Runtime hash with ordinal 1, engine `chatgpt`, kind `llm`, model `sol` |
| Job activation | One-step plan and process identity | `create_job` / `activate_job` | Job hash; active zset maps its key to score 0 |
| Client completion | Successful enqueue subprocess | Git submitted event and SQLite update | Submitted event 305 |

The successful trace contains no exception events. This verification stops at the requested runtime boundary: the materialized runtime and active job exist. Engine execution and response/writeback are not claimed.

### Verification instructions and Redis state

| Control identity | Exact Git path | Materialized Redis key | TTL immediately after activation |
|---|---|---|---|
| `rol_SYMR6P5K1VNX68EZ` | `instructions/Redrafting Editor Role.md` | `instruction:01M1VDTV7VVCTWZQEQJTK0VKXG:record` | 259,199,959 ms |
| `ctx_6FR6QK42XASKBYJW` | `context/HHP Client Case Review.md` | `instruction:01M1VDTV83514H0R2H5GASZXGX:record` | 259,199,966 ms |
| `tsk_CVVNKBJK4ZRWK11P` | `instructions/Prepare Pro Bono Position Paper Boxout for Client Review.md` | `instruction:01M1VDTV89HZDZ3FZ326TKM83D:record` | 259,199,971 ms |

Each instruction hash contains actual fields `content_sha256`, `source_fingerprint`, `title`, `control_identity`, `content`, `extra_json`, and generated `identity`. The trace records the Git source, parsed frontmatter/body, and materialization input. Full contents and exact values are in the linked snapshot, rather than inferred from the plan.

Other reached state:

- `call:01M1VDTTGG4BPKVXKDJ8VESXNK:record`: content and source metadata; call TTL configured and observed at save as 2,592,000 seconds. `store_call` replaces the slugmap and deletes its superseded call key; the earlier calls remain captured in audit snapshots.
- `state:slugmap:index`: source slug → successful call key, no expiry.
- `state:instruction_materializations:index`: the three Control identities → their exact instruction keys above, no expiry.
- `runtime:01M1VDTTGG4BPKVXKDJ8VESXNK:1`: actual fields `engine`, `total_steps`, `instruction_keys`, `ordinal`, `label`, `plan_identity`, `identity`, `engine_kind`, `model`; TTL 86,399,978 ms at activation snapshot. Empty plan `args` is not a field in the persisted hash; the observed hash is reproduced exactly in the evidence.
- `job:01M1VDTTGG4BPKVXKDJ8VESXNK:record`: `identity`, `plan_identity`, `total_steps`, `result_ordinal_hint`, `task_ordinal_hint`, `task_created_at_hint`, `created_at`; no expiry.
- `state:active:index`: zset contains that job key at score 0; no expiry.
- No new failure or response record was created by the successful attempt. Four earlier failure hashes remain: the original two and the instrumentation-induced two below.

### Instrumentation limitation and cleanup

The first attempt of the fresh commit generated process `01M1VDS36ZW9XB1B2MW3W0MDQT`. The diagnostic JSON logger used `repr()` on `self` at entry to the generated Plan constructor, before its attributes had been assigned. That raised `AttributeError: 'asc.models.control.plan.Plan' object has no attribute 'identity'` at `<string>.__repr__`, creating `failure:01M1VDS3FBZEVXZDVEJZMJ9NQC:record` and `failure:01M1VDS3FCN8T66FCAMVK09XMP:record` (SQLite event 304). This is an audit-induced error, not an independent application failure.

The logger was corrected to omit only uninitialized constructor `self`. The same fresh dispatch commit was retried; no third dispatch commit was created and no application semantics were repaired to bypass an error. This is a disclosed deviation from the requested one-attempt verification. Both attempts and their Redis state are retained as evidence.

The temporary Rust edits were restored and verified byte-for-byte against their captured originals. The temporary tracing module, executable audit build, Git wrapper and operational-only script were removed after verification. No permanent tracing infrastructure remains. Redis failures were preserved rather than erased.

No broad tests were run. Narrow checks completed: source Git/disk equality, exact client/receiver and before/after payload equality, observed constructor values, exact operational/authored Git-tree equality, instruction materialization, runtime and active-job state, SQLite/Git submission lineage, and source-restoration equality.

## Evidence files

- [Actual function events and boundary snapshots](/tmp/asc-dispatch-audit/run1-trace.ndjson)
- [Actual executed commands](/tmp/asc-dispatch-audit/run1-exec.log)
- [Client and failure log](/tmp/asc-dispatch-audit/run1-stderr.log)
- [Client payload](/tmp/asc-dispatch-audit/run1-client-payload.json)
- [Received payload](/tmp/asc-dispatch-audit/run1-received-payload.json)
- [Final Redis values and TTLs](/tmp/asc-dispatch-audit/run1-redis-final.json)
- [SQLite identity and events](/tmp/asc-dispatch-audit/sqlite-run1.json)
- [Proposed full publication diff](/tmp/asc-dispatch-audit/proposed-full-publication.diff)


- [Successful verification trace](/tmp/asc-dispatch-audit/run2-retry-trace.ndjson)
- [Verified payloads and constructor values](/tmp/asc-dispatch-audit/run2-verification.json)
- [Redis snapshot at successful activation](/tmp/asc-dispatch-audit/run2-boundary-snapshot.json)
- [Final Redis state](/tmp/asc-dispatch-audit/run2-redis-final.json)
- [Fresh dispatch SQLite events](/tmp/asc-dispatch-audit/sqlite-run2.json)
- [Instrumentation failure evidence](/tmp/asc-dispatch-audit/run2-instrumentation-failure-redis.json)
- [Operational publication log](/tmp/asc-dispatch-audit/publication-operational.log)
- [Published operational tree](/tmp/asc-dispatch-audit/publication-tree.txt)
