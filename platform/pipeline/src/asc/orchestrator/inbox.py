"""Deprecated compatibility surface; orchestration uses state:active:index."""

def count() -> int: return 0
def clear() -> int: return 0
def claim(): return None
def daemon_claim(*, timeout: int = 0, empty_limit=None): return None

__all__ = ["claim", "clear", "count", "daemon_claim"]
