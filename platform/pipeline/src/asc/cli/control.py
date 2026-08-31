import json
import sys

import typer

from asc.control.list import list_control_slugs
from asc.control.repository import delete_plan as delete_plan_record
from asc.control.repository import plan_records, save_plan as save_plan_record
from asc.control.snapshot import build_control_snapshot


app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Read Git-authoritative controls and persist server-side plans.",
)


@app.command("snapshot")
def snapshot() -> None:
    """Emit the published Git control snapshot as JSON."""
    _json_command("snapshot", build_control_snapshot)


@app.command("list")
def list_control() -> None:
    """List published plan and instruction slugs from Git."""
    try:
        for slug in list_control_slugs():
            typer.echo(slug)
    except Exception as exc:
        _fail("list", exc)


@app.command("plans")
def plans(scope: str | None = typer.Option(None, "--scope", help="Optional plan scope.")) -> None:
    """Emit current server-side plans, optionally restricted by scope."""
    _json_command("plans", lambda: plan_records(scope=scope))


@app.command("save-plan")
def save_plan() -> None:
    """Read one plan JSON object from stdin and commit it to the plan repo."""
    try:
        value = json.load(sys.stdin)
        if not isinstance(value, dict):
            raise TypeError("plan input must be a JSON object")
        typer.echo(json.dumps(save_plan_record(value), sort_keys=True))
    except Exception as exc:
        _fail("save-plan", exc)


@app.command("delete-plan")
def delete_plan(identity: str = typer.Argument(..., help="Plan slug to delete.")) -> None:
    """Delete one plan from the server-side plan repository."""
    try:
        typer.echo(json.dumps(delete_plan_record(identity), sort_keys=True))
    except Exception as exc:
        _fail("delete-plan", exc)


@app.command("instruction-manifest")
def instruction_manifest() -> None:
    """Emit lightweight instruction synchronization metadata from Git."""
    try:
        snapshot_value = build_control_snapshot()
        typer.echo(json.dumps({
            "schema_version": 2,
            "type": "autoscribe.instruction-manifest",
            "instructions": snapshot_value.get("registries", {}).get("instructions", {}),
        }, sort_keys=True))
    except Exception as exc:
        _fail("instruction-manifest", exc)


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
