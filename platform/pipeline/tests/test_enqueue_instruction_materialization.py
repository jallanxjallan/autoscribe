from __future__ import annotations

from dataclasses import replace

import pytest
import ulid

from asc.control.repository import GitInstruction
from asc.enqueue import instruction as resolver
from asc.enqueue import runtime
from asc.models.control.instruction import Instruction
from asc.redis.key import RedisKey

IDENTITY = "spc_3N6K8R2V7M4Q9D1X"
REVISION = "a" * 40


def _source():
    return GitInstruction(
        identity=IDENTITY,
        title="Task",
        content="Do the thing.\n",
        path="instructions/task.md",
        revision=REVISION,
        fingerprint="b" * 40,
        extra={},
    )


@pytest.fixture
def materializations(monkeypatch):
    records, pointers, ttls = {}, {}, {}

    class FakeIndex:
        def get(self, identity):
            return pointers.get(identity)

        def set(self, identity, key):
            pointers[identity] = key

    def save(instruction, *, ttl=None):
        records[instruction.raw_key] = instruction.dump_json()
        ttls[instruction.raw_key] = ttl
        return instruction.raw_key

    def hgetall(key):
        return records.get(str(key), {})

    monkeypatch.setattr(resolver, "InstructionMaterializations", FakeIndex)
    monkeypatch.setattr(Instruction, "save", save)
    monkeypatch.setattr(RedisKey, "hgetall", hgetall)
    monkeypatch.setattr(RedisKey, "ttl", lambda key: ttls.get(str(key), -2))
    monkeypatch.setattr(
        resolver, "read_instruction", lambda identity, revision: _source()
    )
    return records, pointers, ttls


def test_new_materialization_has_runtime_ulid_and_configured_ttl(materializations):
    records, pointers, ttls = materializations
    key = resolver.resolve_instruction_key(IDENTITY, control_revision=REVISION)
    instruction = Instruction.load(key)
    assert ulid.ULID.from_str(instruction.identity)
    assert instruction.identity != IDENTITY
    assert instruction.control_identity == IDENTITY
    assert instruction.source_fingerprint == _source().fingerprint
    assert instruction.content == _source().content
    assert ttls[key] == resolver.INSTRUCTION_TTL_SECONDS
    assert pointers == {IDENTITY: key}


def test_same_version_reuses_without_ulid_timestamp(materializations, monkeypatch):
    key = resolver.resolve_instruction_key(IDENTITY, control_revision=REVISION)
    monkeypatch.setattr(
        ulid.ULID, "from_str", lambda *args: pytest.fail("ULID freshness used")
    )
    assert resolver.resolve_instruction_key(IDENTITY, control_revision=REVISION) == key


def test_new_blob_preserves_old_record_and_runtime_reference(
    materializations, monkeypatch
):
    records, pointers, ttls = materializations
    first = resolver.resolve_instruction_key(IDENTITY, control_revision=REVISION)
    old_record = dict(records[first])
    runtime_reference = {"task": [first]}
    source_b = replace(
        _source(), fingerprint="c" * 40, content="New instructions.", revision="d" * 40
    )
    monkeypatch.setattr(
        resolver, "read_instruction", lambda identity, revision: source_b
    )
    second = resolver.resolve_instruction_key(
        IDENTITY, control_revision=source_b.revision
    )
    assert first != second
    assert records[first] == old_record
    assert Instruction.load(runtime_reference["task"][0]).content == _source().content
    assert Instruction.load(second).content == "New instructions."
    assert pointers[IDENTITY] == second


@pytest.mark.parametrize(
    "ttl", [-2, -1, 0, resolver.MIN_REMAINING_INSTRUCTION_TTL_SECONDS - 1]
)
def test_insufficient_ttl_creates_new_version(materializations, ttl):
    records, pointers, ttls = materializations
    first = resolver.resolve_instruction_key(IDENTITY, control_revision=REVISION)
    ttls[first] = ttl
    assert (
        resolver.resolve_instruction_key(IDENTITY, control_revision=REVISION) != first
    )


def test_ttl_boundary_reuses(materializations):
    records, pointers, ttls = materializations
    first = resolver.resolve_instruction_key(IDENTITY, control_revision=REVISION)
    ttls[first] = resolver.MIN_REMAINING_INSTRUCTION_TTL_SECONDS
    assert (
        resolver.resolve_instruction_key(IDENTITY, control_revision=REVISION) == first
    )


def test_identity_mismatch_or_missing_record_is_not_reused(materializations):
    records, pointers, ttls = materializations
    first = resolver.resolve_instruction_key(IDENTITY, control_revision=REVISION)
    records[first]["control_identity"] = "spc_0000000000000000"
    second = resolver.resolve_instruction_key(IDENTITY, control_revision=REVISION)
    assert second != first
    del records[second]
    assert (
        resolver.resolve_instruction_key(IDENTITY, control_revision=REVISION) != second
    )


def test_instruction_arrays_and_revision_forwarding(monkeypatch):
    seen = []

    def resolve(identity, *, control_revision):
        seen.append((identity, control_revision))
        return "instruction:runtime:record"

    monkeypatch.setattr(runtime, "resolve_instruction_key", resolve)
    refs = {"instructions": {"role": [], "context": [], "task": [IDENTITY, IDENTITY]}}
    keys = runtime._resolve_instruction_keys(refs, ordinal=1, control_revision=REVISION)
    assert keys == {"task": ["instruction:runtime:record"] * 2}
    assert seen == [(IDENTITY, REVISION)]


@pytest.mark.parametrize(
    "step",
    [
        {"instruction": "tsk.one"},
        {"instruction_slugs": {}},
        {"instructions": [IDENTITY]},
        {"instructions": {"task": IDENTITY}},
    ],
)
def test_runtime_rejects_legacy_instruction_shapes(step):
    with pytest.raises(ValueError):
        runtime._resolve_instruction_keys(step, ordinal=1, control_revision=REVISION)


def test_old_durable_record_can_drain_but_cannot_be_reused(materializations):
    records, pointers, ttls = materializations
    key = "instruction:01ARZ3NDEKTSV4RRFFQ69G5FAV:record"
    records[key] = {
        "identity": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "slug": "tsk.one",
        "title": "Old task",
        "content": "Old body",
        "source_modified_ns": "1",
        "source_size": "8",
    }
    ttls[key] = resolver.INSTRUCTION_TTL_SECONDS
    assert Instruction.load(key).content == "Old body"
    assert not resolver._can_reuse(key, _source())
    with pytest.raises(ValueError):
        Instruction(slug="tsk.one", title="Old", content="Legacy source rejected")


def test_directive_remains_call_scoped(materializations):
    instruction = runtime._save_directive_instruction(
        call_identity="call-ulid", content="Directive"
    )
    assert instruction.identity == "call-ulid"
    assert instruction.control_identity == ""
    assert instruction.ttl() == runtime.DIRECTIVE_TTL_SECONDS
