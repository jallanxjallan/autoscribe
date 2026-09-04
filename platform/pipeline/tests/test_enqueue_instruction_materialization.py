from __future__ import annotations

from types import SimpleNamespace

import ulid

from asc.control.repository import GitInstruction
from asc.enqueue import instruction as resolver
from asc.enqueue import runtime


def _source(*, committed_at: int = 1) -> GitInstruction:
    return GitInstruction(
        slug="tsk.one",
        title="Task One",
        content="Do the thing.",
        path="instructions/task.md",
        revision="abc123",
        commit_timestamp=committed_at,
        extra={},
    )


def test_missing_slugmap_entry_materializes_ulid_with_configured_ttl(monkeypatch):
    captured = {}

    class FakeSlugMap:
        def get(self, slug):
            return None

        def set(self, slug, key):
            captured["mapping"] = (slug, key)

    def save(instruction, *, ttl=None):
        captured["instruction"] = instruction
        captured["ttl"] = ttl
        return instruction.raw_key

    monkeypatch.setattr(resolver, "read_instruction", lambda slug: _source())
    monkeypatch.setattr(resolver, "SlugMap", FakeSlugMap)
    monkeypatch.setattr(resolver.Instruction, "save", save)

    key = resolver.resolve_instruction_key("tsk.one")

    assert key.startswith("instruction:")
    assert ulid.ULID.from_str(captured["instruction"].identity)
    assert captured["ttl"] == resolver.INSTRUCTION_TTL_SECONDS
    assert captured["mapping"] == ("tsk.one", key)


def test_current_key_is_reused_only_with_safe_remaining_ttl(monkeypatch):
    identity = str(ulid.ULID())

    class FakeKey:
        kind = "instruction"
        suffix = "record"

        def __init__(self, value):
            self.identity = identity

        def ttl(self):
            return resolver.MIN_REMAINING_INSTRUCTION_TTL_SECONDS

    monkeypatch.setattr(resolver, "RedisKey", FakeKey)
    monkeypatch.setattr(
        resolver.Instruction,
        "load",
        lambda key: SimpleNamespace(slug="tsk.one"),
    )

    assert resolver._can_reuse(
        f"instruction:{identity}:record",
        _source(committed_at=1),
    )


def test_low_ttl_or_stale_ulid_is_not_reused(monkeypatch):
    identity = str(ulid.ULID())

    class FakeKey:
        kind = "instruction"
        suffix = "record"

        def __init__(self, value):
            self.identity = identity

        def ttl(self):
            return resolver.MIN_REMAINING_INSTRUCTION_TTL_SECONDS - 1

    monkeypatch.setattr(resolver, "RedisKey", FakeKey)
    assert not resolver._can_reuse(
        f"instruction:{identity}:record",
        _source(committed_at=1),
    )

    assert not resolver._can_reuse(
        f"instruction:{identity}:record",
        _source(committed_at=int(ulid.ULID.from_str(identity).timestamp) + 1),
    )


def test_plan_instruction_labels_are_resolved_before_runtime_storage(monkeypatch):
    monkeypatch.setattr(
        runtime,
        "resolve_instruction_key",
        lambda slug: f"instruction:{slug}:record",
    )

    keys = runtime._resolve_instruction_keys(
        {
            "instruction_slugs": {
                "context": "ctx.project",
                "instructions": "tsk.one",
            }
        },
        ordinal=1,
    )

    assert keys == {
        "context": "instruction:ctx.project:record",
        "task": "instruction:tsk.one:record",
    }
