from __future__ import annotations

import json

import typer

from asc.control.snapshot import build_control_snapshot


app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Inspect the live reusable pipeline component catalogue.",
)


@app.command("snapshot")
def snapshot() -> None:
    """Emit instructions, engines, models, scripts, and profiles as JSON."""
    try:
        payload = build_control_snapshot()
        if not isinstance(payload, dict):
            raise TypeError("component snapshot must be an object")
        payload = dict(payload)
        payload["type"] = "autoscribe.components"
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    except Exception as exc:
        typer.echo(f"[components:snapshot] error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
