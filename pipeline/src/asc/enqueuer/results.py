from __future__ import annotations

from asc.state.results_index import ResultsIndex


def create_results_index(
    *,
    identity: str,
    call_identity: str,
    total_steps: int,
    ttl_seconds: int | None = None,
) -> ResultsIndex:
    """Create the process results index and record the originating Call identity."""

    if not identity:
        raise ValueError("identity must be non-empty")
    if not call_identity:
        raise ValueError("call_identity must be non-empty")
    if total_steps < 1:
        raise ValueError("total_steps must be positive")

    results_index = ResultsIndex.create(
        identity=identity,
        total_steps=total_steps,
        ttl_seconds=ttl_seconds,
    )
    results_index.set_slot(0, call_identity)
    return results_index.redis_key


__all__ = ["create_results_index"]
