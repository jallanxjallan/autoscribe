"""Read the live control slug catalog."""

from asc.state.slugmap import SlugMap


def list_control_slugs() -> list[str]:
    """Return current control slugs in stable order.

    ``SlugMap.list()`` is the authoritative live slug -> Redis key mapping.
    Do not maintain a second listing API or cached control registry here.
    """
    return sorted(SlugMap().list())


__all__ = ["list_control_slugs"]
