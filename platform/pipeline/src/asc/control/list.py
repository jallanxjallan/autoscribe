"""List permanent Control instruction identities and plan slugs."""

from asc.control.repository import list_revision


def list_control_identities() -> list[str]:
    snapshot = list_revision()
    return sorted([*snapshot.instructions, *snapshot.plans])
