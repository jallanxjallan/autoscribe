from __future__ import annotations

from dataclasses import dataclass

from asc.enqueuer.reader import EnqueueRecord
from asc.state.slugmap import SlugKeyResolver


@dataclass(frozen=True, slots=True)
class ResolvedEnqueueKeys:
    plan_key: str


def resolve_enqueue_keys(record: EnqueueRecord) -> ResolvedEnqueueKeys:
    resolver = SlugKeyResolver()
    return ResolvedEnqueueKeys(
        plan_key=resolver.resolve(record.plan_slug, expected_kind="plan"),
    )


__all__ = ["ResolvedEnqueueKeys", "resolve_enqueue_keys"]
