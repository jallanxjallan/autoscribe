"""Build the Git-authoritative control snapshot consumed by clients."""

from typing import Any

from asc.control.extensions import build_extension_catalog
from asc.control.repository import control_checkout, instruction_records, plan_records


def build_control_snapshot() -> dict[str, Any]:
    """Return the current published control catalog from Git, not Redis."""
    instructions = {record["slug"]: record for record in instruction_records()}
    plans = {str(record["record_identity"]): record for record in plan_records()}
    with control_checkout() as published_control:
        extension_catalog = build_extension_catalog(published_control)
    extension_registries = extension_catalog.get("registries", {})
    return {
        "schema_version": 3,
        "type": "autoscribe.controls",
        "source": {"authority": "git", "extensions": extension_catalog.get("sources", {})},
        "registries": {
            "instructions": instructions,
            "plans": plans,
            "engines": dict(extension_registries.get("engines", {})),
            "models": dict(extension_registries.get("models", {})),
            "local_scripts": dict(extension_registries.get("local_scripts", {})),
            "rag_profiles": dict(extension_registries.get("rag_profiles", {})),
        },
        "stale": {},
    }


__all__ = ["build_control_snapshot"]
