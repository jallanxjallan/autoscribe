"""Preferred runtime materialization, indexed by permanent Control identity.

A pointer is a cache hint only. Readers verify identity, fingerprint and TTL;
concurrent writers may create independent valid versions without CAS or deletion.
"""

from typing import ClassVar

from asc.redis.index_base import FixedRedisHashIndex


class InstructionMaterializations(FixedRedisHashIndex):
    KEY: ClassVar[str] = "state:instruction_materializations:index"

    def get(self, identity: str) -> str | None:
        return self.hget(identity)

    def set(self, identity: str, key: str) -> None:
        self.hset(field=identity, value=key)
