"""Build the Git-authoritative Control snapshot consumed by clients."""

from typing import Any

from asc.control.repository import accept_revision, instruction_records, plan_records


def build_control_snapshot() -> dict[str, Any]:
    """Return one accepted Git snapshot, including pinned capability metadata."""
    snapshot = accept_revision()
    instructions = {
        record["identity"]: record for record in instruction_records(snapshot)
    }
    plans = {record["slug"]: record for record in plan_records(snapshot=snapshot)}
    return {
        "schema_version": 4,
        "type": "autoscribe.controls",
        "source": {
            "authority": "git",
            "revision": snapshot.revision,
        },
        "registries": {
            "instructions": instructions,
            "plans": plans,
            **snapshot.capabilities,
        },
        "stale": {},
    }


__all__ = ["build_control_snapshot"]
