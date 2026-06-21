"""Small Redis-key helpers for orchestrator routing.

This module intentionally centralizes key interpretation so handlers do not
split strings directly.  When RedisKey grows final kind/identity/suffix helpers,
this file should become almost trivial.
"""

from __future__ import annotations

from dataclasses import dataclass

from asc.redis.key import RedisKey

from .contracts import COMMITTED_STEP_PREFIX
from .errors import OrchestratorContractError


@dataclass(frozen=True, slots=True)
class RuntimeKey:
    raw: str
    kind: str
    identity: str
    suffix: str | None = None

    @classmethod
    def parse(cls, key: str | RedisKey) -> "RuntimeKey":
        redis_key = key if isinstance(key, RedisKey) else RedisKey(str(key))
        raw = str(redis_key)
        kind = _required(getattr(redis_key, "kind", None), "key.kind", raw)
        identity = _required(getattr(redis_key, "identity", None), "key.identity", raw)
        suffix = getattr(redis_key, "suffix", None)
        if suffix is not None:
            suffix = str(suffix).strip() or None
        return cls(raw=raw, kind=kind, identity=identity, suffix=suffix)

    def require_suffix(self) -> str:
        if not self.suffix:
            raise OrchestratorContractError(f"posted {self.kind!r} key has no suffix: {self.raw}")
        return self.suffix


def _required(value: object, name: str, raw: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise OrchestratorContractError(f"{name} is missing from Redis key: {raw}")
    return text


def _parse_step_suffix(key: RuntimeKey, *, label: str) -> int:
    suffix = key.require_suffix()
    if suffix.startswith(COMMITTED_STEP_PREFIX):
        suffix = suffix.removeprefix(COMMITTED_STEP_PREFIX)
    try:
        step_number = int(suffix)
    except ValueError as exc:
        raise OrchestratorContractError(f"{label} key suffix is not a step number: {key.raw}") from exc
    if step_number < 1:
        raise OrchestratorContractError(f"{label} step must be >= 1: {key.raw}")
    return step_number


def response_step_number(key: RuntimeKey) -> int:
    return _parse_step_suffix(key, label="response")


def committed_step_number(key: RuntimeKey) -> int:
    return _parse_step_suffix(key, label="committed")


__all__ = ["RuntimeKey", "committed_step_number", "response_step_number"]
