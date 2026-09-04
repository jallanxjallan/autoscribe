import json

import typer

from asc.control.list import list_control_slugs
from asc.control.repository import plan_records
from asc.control.snapshot import build_control_snapshot


app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Read Git-authoritative instructions and plans from published Control.",
)


@app.command("snapshot")
def snapshot() -> None:
    """Emit the published Git Control snapshot as JSON."""
    _json_command("snapshot", build_control_snapshot)


@app.command("list")
def list_control() -> None:
    """List published instruction and plan slugs from Control Git."""
    try:
        for slug in list_control_slugs():
            typer.echo(slug)
    except Exception as exc:
        _fail("list", exc)


@app.command("plans")
def plans(scope: str | None = typer.Option(None, "--scope", help="Optional plan scope.")) -> None:
    """Emit published plans from Control Git, optionally restricted by scope."""
    _json_command("plans", lambda: plan_records(scope=scope))


def _json_command(name: str, function) -> None:
    try:
        typer.echo(json.dumps(function(), indent=2, sort_keys=True))
    except Exception as exc:
        _fail(name, exc)


def _fail(name: str, exc: Exception) -> None:
    typer.echo(f"[control:{name}] error: {exc}", err=True)
    raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
