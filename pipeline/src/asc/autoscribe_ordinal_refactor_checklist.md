# AutoScribe ordinal refactor checklist

Date: 2026-07-08

## Purpose

Separate two meanings that are currently both being handled as `suffix`:

- `suffix`: a static subtype/facet of an identity, such as `record` or `index`.
- `ordinal`: an ordered key tail, such as step 1, result 1, failure 1.

Target doctrine:

```text
call:<identity>:record     suffix
call:<identity>:index      suffix
plan:<identity>:record     suffix
plan:<identity>:index      suffix

step:<identity>:1          ordinal
step:<identity>:2          ordinal
response:<identity>:1      ordinal
transform:<identity>:1     ordinal
retrieval:<identity>:1     ordinal
failure:<identity>:1       ordinal
```

Keep `step_number` in the SQLite ledger/reporting layer for now. This pass is about Redis model addressing and runtime contracts, not ledger schema migration.

---

Yes. **Merge the current dev branch first**, but do it deliberately.

Since your current `dev` is now vastly different from `master`, creating another branch before merging will just give you a second moving target. You will end up wondering whether bugs belong to the old pipeline work, the new branch work, or the merge boundary.

I would do this:

```bash
git status
```

Make sure the working tree is clean.

```bash
git add -A
git commit -m "Complete pipeline refactor before merge"
```

Then tag the current state so you have a rollback point:

```bash
git tag pre-pipeline-merge-20260708
```

Switch to master and merge:

```bash
git checkout master
git merge dev --no-ff
```

Then run the basic smoke tests from `master`:

```bash
asc run status
asc run log
asc run drain
```

Assuming that holds together, create the next branch from the merged master:

```bash
git checkout -b ordinal-save-refactor
```

For the specific suffix/ordinal work, I would **not** do it on top of the already-huge dev branch. That change cuts across model identity, key naming, save behavior, and step/result semantics. It deserves a clean branch whose diff says exactly that.

So the rule of thumb here:

**Current dev = merge boundary.**
**Ordinal/save cleanup = new branch after merge.**


---

## 1. Baseline grep

Run this first and save the output somewhere if useful:

```bash
cd /home/jeremy/AutoScribe/pipeline/src
rg -n "Step\.suffix|model_post_init|step_number|result_suffix|Field\(alias=\"suffix\"\)|Step\(RedisMessage|suffix: ClassVar|\.number\b|\.ordinal\b|RESULT_KIND_BY_ENGINE" asc
```

Also check external engines, because they may instantiate `Response`, `Transform`, `Retrieval`, `Failure`, or `Result` directly:

```bash
rg -n "step_number|result_suffix|suffix=|step\.number|step\.ordinal|Response\(|Transform\(|Retrieval\(|Failure\(|Result\(" /home/jeremy/AutoScribe/extensions
```

---

## 2. Patch `asc/redis/model_base.py`

Goal: keep `save()` clean everywhere, but teach the base model how to resolve the third Redis key segment.

Rules:

1. explicit raw key wins
2. explicit `save(..., suffix=x)` wins
3. subclass-declared static `suffix` wins
4. instance `ordinal` wins
5. otherwise no third key segment

Important detail: do not use plain `getattr(cls, "suffix")` to decide whether a class has a static suffix. The base class declares `suffix = None`, so inherited `None` masks the distinction between “no static suffix declared” and “static suffix declared on this subclass.”

Use `"suffix" in cls.__dict__` to detect a subclass-declared static suffix.

Suggested operations:

- Add a class helper such as `_static_suffix()`:

```python
@classmethod
def _static_suffix(cls) -> str | int | None | object:
    if "suffix" in cls.__dict__:
        return cls.__dict__["suffix"]
    return _UNSET
```

- Add an instance helper such as `_implicit_suffix()`:

```python
def _implicit_suffix(self) -> str | int | None:
    static = self.__class__._static_suffix()
    if static is not _UNSET:
        return static

    ordinal = getattr(self, "ordinal", _UNSET)
    if ordinal is not _UNSET:
        return ordinal

    return None
```

- Change `key_for_identity()` so it uses `_static_suffix()` instead of `cls.suffix` when no explicit suffix is supplied.

- Change `redis_key` so it uses the instance’s implicit suffix.

- Change `save()` so if `suffix` is `_UNSET`, it uses `self._implicit_suffix()`.

Do not rename the low-level `RedisKey(..., suffix=...)` API. At that layer, `suffix` still means the physical third key segment.

---

## 3. Patch `asc/models/control/step.py`

Goal: `Step` is reusable plan data, not a runtime queue message.

Operations:

- Change inheritance:

```python
from asc.redis.model_base import RedisModel

class Step(RedisModel):
```

- Remove:

```python
from typing import Any
from asc.core.identity import generate_identity
from asc.redis.message_base import RedisMessage
suffix: ClassVar[str] = ""
def model_post_init(...): ...
step_number: int
```

- Add:

```python
ordinal: int
```

- Keep a convenience property if you want existing code to read cleanly:

```python
@property
def number(self) -> int:
    return self.ordinal
```

- Update serializer:

```python
@field_serializer("created_at", "ordinal")
def serialize_ints(self, value: int) -> str:
    return str(value)
```

- Update docstring language:

```text
Step keys use the Plan identity plus the numeric ordinal:
    step:<plan_identity>:<ordinal>

Only `ordinal` and `engine` are part of the core execution contract.
```

Expected final shape:

```python
class Step(RedisModel):
    model_config = ConfigDict(extra="allow")

    kind: ClassVar[str] = "step"

    identity: str
    ordinal: int
    engine: str
    created_at: int = Field(default_factory=timestamp)

    @property
    def number(self) -> int:
        return self.ordinal
```

No `suffix` ClassVar. No `model_post_init`. No `step_number` field.

---

## 4. Patch `asc/ingest/handlers/plan.py`

Goal: materialized Step records store `ordinal`, not `step_number`.

Operations:

- In `_step_payload()`, change:

```python
"step_number": number,
```

to:

```python
"ordinal": number,
```

- Leave this clean call intact:

```python
step_key = step.save(ttl=STEP_TTL_SECONDS)
```

After the `RedisModel` base patch, this should save as:

```text
step:<plan_identity>:<ordinal>
```

- Optional naming cleanup only: `_step_number()` can stay if it describes uploaded plan numbering. Or rename to `_step_ordinal()` if you want the ingest terminology fully aligned.

---

## 5. Patch `asc/orchestrator/tasks/worker.py`

Goal: worker task factories should derive result/failure keys from the Step ordinal and validate that the key tail agrees.

Operations:

- Rename helper conceptually from `_step_suffix()` to `_step_ordinal()`.

- Replace tolerant fallback logic with a hard integrity check:

```python
def _step_ordinal(*, step_key: str, step: Step) -> str:
    ordinal = str(step.ordinal)
    key_ordinal = RedisKey(step_key).suffix

    if str(key_ordinal) != ordinal:
        raise ValueError(
            f"step ordinal/key mismatch: key={step_key!r} ordinal={ordinal!r}"
        )

    return ordinal
```

- Continue to construct physical Redis keys with `suffix=ordinal`:

```python
RedisKey(
    kind=result_kind,
    identity=RedisKey(data_key).identity,
    suffix=_step_ordinal(step_key=step_key, step=step),
).raw_key
```

Same for `failure`.

- Do not add fallback to `step_number`.

---

## 6. Patch `asc/orchestrator/handlers/call_index.py`

Goal: this file mostly stays as-is; only terminology should change.

Operations:

- Keep checking the physical key tail:

```python
suffix = required_text(key.suffix, ...)
```

- Change error wording from “step suffix” to “step ordinal”:

```python
f"step ordinal must match call index slot: slot {slot}, key {step_key!r}"
```

- Leave `RESULT_KINDS` unchanged unless doing the separate result-kind unification pass.

---

## 7. Patch `asc/worker/execute.py`

Goal: worker execution should validate artifact ordinals, not `result_suffix` or `step_number`.

Operations:

- Replace `_step_number(step)` with `_step_ordinal(step)`:

```python
def _step_ordinal(step: Step) -> str:
    value = getattr(step, "ordinal", None)
    if value in (None, ""):
        raise ValueError("step.ordinal must not be empty")
    return str(value)
```

- Replace reads of:

```python
step.step_number
artifact.result_suffix
getattr(artifact, "result_suffix", ...)
```

with:

```python
step.ordinal
artifact.ordinal
```

- Runtime failure creation should pass:

```python
"ordinal": step.ordinal,
```

not:

```python
"suffix": step_number,
```

- In diagnostic `raw_json`, prefer:

```python
"step_ordinal": step.ordinal,
```

rather than `step_number`. If you want to preserve human readability, it is okay to include both, but do not make `step_number` a runtime contract.

- Artifact validation should check:

```text
artifact.identity == expected.identity
artifact.ordinal == expected.suffix
artifact.raw_key == expected.raw_key
```

The `expected.suffix` name is still from `RedisKey`, so that is fine.

---

## 8. Patch `asc/models/process/result.py`

Goal: remove the custom `result_suffix` workaround once the base class understands `ordinal`.

Operations for `Result`:

- Replace:

```python
result_suffix: str = Field(alias="suffix")
```

with:

```python
ordinal: int
```

- Remove custom `redis_key`, `raw_key`, and `save()` overrides if the base class now handles `ordinal`.

- Update `output_key_for()` to accept `ordinal`, or keep its external parameter as `suffix` only if callers still use it. Preferred:

```python
@classmethod
def output_key_for(cls, *, identity: object, ordinal: object) -> str:
    return RedisKey(kind=cls.kind, identity=_identity(identity), suffix=_step_ordinal(ordinal)).raw_key
```

- Rename `validate_result_suffix()` to validate `ordinal`.

Operations for `Failure`:

- Replace:

```python
result_suffix: str | None = Field(default=None, alias="suffix")
```

with:

```python
ordinal: int | None = None
```

- Remove custom `redis_key`, `raw_key`, and `save()` overrides if possible.

- In `Failure.external()`, change:

```python
suffix=getattr(step, "step_number")
```

to:

```python
ordinal=getattr(step, "ordinal")
```

- In `InternalFailure.from_exception()`, change:

```python
suffix=context.get("suffix")
```

to:

```python
ordinal=context.get("ordinal")
```

- Adjust validators/helpers from `_step_suffix` / `_optional_suffix` to `_step_ordinal` / `_optional_ordinal`.

Keep subclasses for now:

```python
Response
Transform
Retrieval
Failure
```

Do not unify them into `Result` in this pass unless you deliberately want a larger cleanup.

---

## 9. Patch external engines if needed

Run this again after the internal model changes:

```bash
rg -n "step_number|result_suffix|suffix=|step\.number|step\.ordinal|Response\(|Transform\(|Retrieval\(|Failure\(|Result\(" /home/jeremy/AutoScribe/extensions
```

Update any engine artifact construction from:

```python
Response(identity=call.identity, suffix=step.step_number, ...)
```

or:

```python
Response(identity=call.identity, result_suffix=..., ...)
```

to:

```python
Response(identity=call.identity, ordinal=step.ordinal, ...)
```

Same for `Transform`, `Retrieval`, and `Failure`.

---

## 10. Leave these alone for now

Do not chase these unless tests prove they are active and broken:

- `asc/cli/orchestrator/*`: appears to be duplicate/older orchestrator code.
- `asc/ledger/writers/*`: likely older duplicate of the active scrivener writer path.
- SQLite schema fields called `step_number`.
- Exporter queries that join on `steps.step_number`.
- CLI display commands that call the ledger field `step_number`.

Active ledger/scrivener code may still calculate ledger `step_number` from the runtime key tail. That is okay. Ledger/reporting vocabulary can stay human-facing.

---

## 11. Post-edit grep

Run:

```bash
cd /home/jeremy/AutoScribe/pipeline/src
rg -n "Step\.suffix|model_post_init|Step\(RedisMessage|result_suffix|Field\(alias=\"suffix\"\)|step\.step_number|getattr\(step, \"step_number\"" asc
```

Expected: no hits in active runtime/model code.

Then run:

```bash
rg -n "step_number" asc
```

Expected allowed leftovers:

```text
asc/ledger/*
asc/scrivener/* ledger writer/reporting functions
asc/exporter/* queries that read ledger step_number
asc/cli/storage.py display/inspect commands
asc/models/control/plan.py helper arguments/docstrings if not renamed
possibly asc/state/calls.py slot helper names
```

Unexpected leftovers:

```text
asc/models/control/step.py
asc/ingest/handlers/plan.py stored Step payload
asc/orchestrator/tasks/worker.py
asc/worker/execute.py
asc/models/process/result.py
external engines that construct runtime artifacts
```

---

## 12. Runtime cleanup

Old Redis records will contain `step_number`, not `ordinal`. Do not support both. Flush or delete the active test keys and re-upload plans.

Suggested conservative cleanup:

```bash
asc run stop
redis-cli --scan --pattern 'step:*' | xargs -r redis-cli DEL
redis-cli --scan --pattern 'plan:*:index' | xargs -r redis-cli DEL
redis-cli --scan --pattern 'call:*' | xargs -r redis-cli DEL
redis-cli --scan --pattern 'task:*' | xargs -r redis-cli DEL
redis-cli --scan --pattern 'response:*' | xargs -r redis-cli DEL
redis-cli --scan --pattern 'transform:*' | xargs -r redis-cli DEL
redis-cli --scan --pattern 'retrieval:*' | xargs -r redis-cli DEL
redis-cli --scan --pattern 'failure:*' | xargs -r redis-cli DEL
```

If the DB is disposable for alpha testing, a full Redis flush is simpler but more destructive:

```bash
redis-cli FLUSHDB
```

Then re-upload instructions/plans/content using your normal commands.

---

## 13. Smoke tests

Start small:

```bash
asc run status
asc run drain
asc run log
```

Check Redis keys:

```bash
redis-cli --scan --pattern 'step:*' | sort
redis-cli --scan --pattern 'response:*' | sort
redis-cli --scan --pattern 'failure:*' | sort
```

Inspect a materialized step:

```bash
redis-cli HGETALL step:<plan_identity>:1
```

Expected fields include:

```text
identity=<plan_identity>
ordinal=1
engine=<engine>
```

Expected fields should not include:

```text
step_number
suffix
```

Inspect a successful result:

```bash
redis-cli HGETALL response:<call_identity>:1
```

Expected fields include:

```text
identity=<call_identity>
ordinal=1
content=...
```

Expected fields should not include:

```text
result_suffix
suffix
```

---

## 14. Commit message

Suggested commit message after tests pass:

```text
Separate static suffixes from ordered key ordinals

Introduce ordinal as the model-level name for ordered Redis key tails used by
step and worker output records, while preserving suffix for static identity
facets such as record and index. Teach RedisModel.save() to resolve subclass
static suffixes before falling back to instance ordinal, convert Step to stable
RedisModel data, and update worker/result paths to validate ordinal/key
alignment without mutating class-level suffix state.
```

---

## 15. Do not mix in this larger cleanup unless deliberately chosen

Result kind unification is separate:

```text
response/transform/retrieval/failure
```

could later become:

```text
result/failure
```

That would touch orchestrator result kinds, scrivener loader mappings, worker task factories, external engines, and export queries. Keep it out of the ordinal refactor unless you want the larger blast radius.
