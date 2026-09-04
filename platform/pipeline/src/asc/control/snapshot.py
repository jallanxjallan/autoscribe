"""Build the Git-authoritative Control snapshot consumed by clients."""

from typing import Any

from asc.control.extensions import build_extension_catalog
from asc.control.repository import instruction_records, plan_records


def build_control_snapshot() -> dict[str, Any]:
    """Return current Git controls and filesystem-backed extensions."""
    instructions = {record["slug"]: record for record in instruction_records()}
    plans = {str(record["record_identity"]): record for record in plan_records()}
    extensions = build_extension_catalog()
    return {
        "schema_version": 3,
        "type": "autoscribe.controls",
        "source": {
            "authority": "git",
            "extensions": extensions["sources"],
        },
        "registries": {
            "instructions": instructions,
            "plans": plans,
            **extensions["registries"],
        },
        "stale": {},
    }


__all__ = ["build_control_snapshot"]
