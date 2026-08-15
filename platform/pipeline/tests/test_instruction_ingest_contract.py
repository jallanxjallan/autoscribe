from __future__ import annotations

import hashlib

from asc.ingest.handlers import instructions as handler


def test_instruction_ingest_persists_sync_metadata_as_model_fields(monkeypatch) -> None:
    captured = {}

    def save(instruction, *, ttl=None):
        captured["instruction"] = instruction
        captured["ttl"] = ttl
        return instruction.raw_key

    class FakeSlugMap:
        def get(self, slug):
            captured["lookup"] = slug
            return None

        def set(self, slug, key):
            captured["mapping"] = (slug, key)

    monkeypatch.setattr(handler.Instruction, "save", save)
    monkeypatch.setattr(handler, "SlugMap", FakeSlugMap)
    monkeypatch.setattr(handler, "expire_old_key", lambda old, new: None)

    content = "Forward-only instruction contract\n"
    result = handler.ingest_instruction(
        {
            "type": "instruction",
            "identity": "tsk.forward.contract",
            "content": content,
            "extra": {
                "title": "Forward Contract",
                "source_path": "tasks/Forward Contract.md",
                "source_modified_ns": "1786170627000000000",
                "source_size": "883",
            },
        }
    )

    instruction = captured["instruction"]
    assert instruction.content_sha256 == hashlib.sha256(content.strip().encode()).hexdigest()
    assert instruction.source_modified_ns == 1786170627000000000
    assert instruction.source_size == 883
    assert result.slug == "tsk.forward.contract"
    assert captured["mapping"] == ("tsk.forward.contract", instruction.raw_key)
