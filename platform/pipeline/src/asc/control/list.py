"""List Git-authoritative control slugs."""

from asc.control.repository import instruction_records, plan_records


def list_control_slugs() -> list[str]:
    return sorted(
        [record["slug"] for record in instruction_records()]
        + [str(record["record_identity"]) for record in plan_records()]
    )


__all__ = ["list_control_slugs"]
