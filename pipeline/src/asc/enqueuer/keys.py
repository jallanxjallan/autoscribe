from __future__ import annotations

from dataclasses import dataclass

from asc.enqueuer.reader import EnqueueRecord
from asc.state.slugmap import SlugKeyResolver


@dataclass(frozen=True, slots=True)
class ResolvedEnqueueKeys:
    call_key: str
    plan_key: str

    @property
    def call_identity(self) -> str:
        return identity_from_key(self.call_key)


def resolve_enqueue_keys(record: EnqueueRecord) -> ResolvedEnqueueKeys:
    resolver = SlugKeyResolver()
    return ResolvedEnqueueKeys(
        call_key=resolver.resolve(record.call_slug, expected_kind="call"),
        plan_key=resolver.resolve(record.plan_slug, expected_kind="plan"),
    )


def identity_from_key(key: str) -> str:
    parts = key.strip().split(":")
    if len(parts) != 3 or not all(parts):
        raise ValueError(f"invalid Redis model key: {key!r}")
    return parts[1]


__all__ = ["ResolvedEnqueueKeys", "identity_from_key", "resolve_enqueue_keys"]
