from __future__ import annotations

from asc.state.slugmap import (
    SLUGMAP_KEY as CONTROL_SLUGMAP_KEY,
    SLUGMAP_TTL_SECONDS as CONTROL_SLUGMAP_TTL_SECONDS,
    SlugMap as ControlSlugMap,
)

__all__ = [
    "CONTROL_SLUGMAP_KEY",
    "CONTROL_SLUGMAP_TTL_SECONDS",
    "ControlSlugMap",
]
