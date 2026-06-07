"""Redis-backed state helpers for AutoScribe runtime coordination.

State modules should be thin adapters over Redis keys. Domain validation belongs in
models; execution policy belongs in execute.
"""

__all__: list[str] = []
