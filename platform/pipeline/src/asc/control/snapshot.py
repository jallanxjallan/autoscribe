"""Build the Git-authoritative Control snapshot consumed by clients."""

from typing import Any

from asc.control.repository import instruction_records, plan_records


def build_control_snapshot() -> dict[str, Any]:
    """Return the current published Control catalog from Git.

    Control contains authored instructions and plans only. Executable engines,
    scripts, models, and other runtime extensions are published separately.
    """
    instructions = {record["slug"]: record for record in instruction_records()}
    plans = {str(record["record_identity"]): record for record in plan_records()}
    return {
        "schema_version": 3,
        "type": "autoscribe.controls",
        "source": {"authority": "git"},
        "registries": {
            "instructions": instructions,
            "plans": plans,
        },
        "stale": {},
    }


__all__ = ["build_control_snapshot"]
