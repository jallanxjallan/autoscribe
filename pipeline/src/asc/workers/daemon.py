"""Thin worker daemon wrapper.

Run with:
    python -m asc.workers.daemon
"""

from __future__ import annotations

from .runtime import main


if __name__ == "__main__":
    main()
