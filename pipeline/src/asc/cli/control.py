from __future__ import annotations

import json
import typer

from asc.control.list import list_control_slugs
from asc.control.snapshot import build_control_snapshot


app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Inspect reusable uploaded control assets.",
)


@app.command("snapshot")
def snapshot() -> None:
    """Emit the live uploaded-control snapshot as JSON."""
    try:
        typer.echo(json.dumps(build_control_snapshot(), indent=2, sort_keys=True))

    except Exception as exc:
        typer.echo(f"[control:snapshot] error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command("list")
def list_control() -> None:
    """List current slugs in the control slugmap."""
    try:
        slugs = list_control_slugs()

    except Exception as exc:
        typer.echo(f"[control:list] error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    for slug in slugs:
        typer.echo(slug)


if __name__ == "__main__":
    app()
