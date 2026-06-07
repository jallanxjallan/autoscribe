from __future__ import annotations

from asc.state.control_slugmap import ControlSlugMap


def list_control_slugs() -> list[str]:
    return ControlSlugMap().list_slugs()