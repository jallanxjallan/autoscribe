"""CLI access to the live extension registry and Obsidian snapshot."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from asc.registries import build_registry_snapshot

app = typer.Typer(
    no_args_is_help=True,
    help="Inspect extensions available to the runtime and Obsidian plan compiler.",
)

REGISTRY_CHOICES = {"engines", "local_scripts", "rag_profiles"}


def _echo_json(value: object) -> None:
    typer.echo(json.dumps(value, indent=2, sort_keys=True))


@app.command("snapshot")
def snapshot() -> None:
    """Emit the current Obsidian plan-compiler snapshot as JSON."""
    _echo_json(build_registry_snapshot())


@app.command("list")
def list_components(
    registry: Annotated[
        str,
        typer.Argument(help="One of: all, engines, local_scripts, rag_profiles."),
    ] = "all",
    *,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit JSON instead of tab-separated rows."),
    ] = False,
) -> None:
    """List extensions discovered from the live extensions folder."""
    registries = build_registry_snapshot()["registries"]

    if registry == "all":
        selected = registries
    elif registry in REGISTRY_CHOICES:
        selected = {registry: registries.get(registry, {})}
    else:
        allowed = ", ".join(["all", *sorted(REGISTRY_CHOICES)])
        raise typer.BadParameter(f"registry must be one of: {allowed}")

    if json_output:
        _echo_json(selected)
        return

    for registry_name, records in selected.items():
        for key, record in records.items():
            label = record.get("label", "")
            kind = record.get("kind", record.get("callable", ""))
            typer.echo(f"{registry_name}\t{key}\t{kind}\t{label}")


__all__ = ["app"]
