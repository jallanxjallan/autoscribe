"""List permanent Control instruction identities and plan slugs."""

from asc.control.repository import accept_revision


def list_control_identities() -> list[str]:
    snapshot = accept_revision()
    return sorted([*snapshot.instructions, *snapshot.plans])
