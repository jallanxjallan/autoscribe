from __future__ import annotations

import json
import sys

import typer

from asc.control.list import list_control_slugs
from asc.control.snapshot import build_control_snapshot
from asc.control.upload import (
    UploadReport,
    upload_instructions_stream,
    upload_plans_stream,
)


app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Inspect and upload reusable control assets.",
)

upload_app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Upload explicitly targeted reusable control records.",
)

app.add_typer(upload_app, name="upload")


def _finish(kind: str, report: UploadReport) -> None:
    typer.echo(
        f"[control:upload:{kind}] uploaded: "
        f"records={report.record_count} skipped={report.skipped_count}",
        err=True,
    )


def _run_upload(kind: str) -> None:
    uploaders = {
        "instructions": upload_instructions_stream,
        "plans": upload_plans_stream,
    }
    uploader = uploaders[kind]

    try:
        report = uploader(sys.stdin)
    except Exception as exc:
        typer.echo(f"[control:upload:{kind}] error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _finish(kind, report)


@upload_app.command("instructions")
def upload_instructions() -> None:
    """Upload instruction records from streamed NDJSON."""
    _run_upload("instructions")

@upload_app.command("plans")
def upload_plans() -> None:
    """Upload plan records from streamed NDJSON."""
    _run_upload("plans")


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
